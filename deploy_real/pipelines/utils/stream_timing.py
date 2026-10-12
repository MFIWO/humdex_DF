"""[추가] PICO-style host-clock resampling for the SONIC joint-reference path.

Reception timestamps are not sensor capture timestamps. Keep that distinction in
logs; never replace a historical reference timestamp with its publication time.
"""
from __future__ import annotations

from collections import deque
import math
import time

import numpy as np


def sleep_until_next_tick(context: dict, target_fps: float) -> None:
    """[추가] Subtract work time and skip expired deadlines without burst loops."""
    if not math.isfinite(target_fps) or target_fps <= 0:
        return
    period = 1.0 / target_fps
    now = time.monotonic()
    start = float(context.get("loop_start_monotonic", now))
    deadline = float(context.get("loop_next_deadline", start + period))
    remaining = deadline - now
    context["loop_work_ms"] = (now - start) * 1000.0
    context["loop_sleep_ms"] = max(0.0, remaining) * 1000.0
    if remaining > 0:
        time.sleep(remaining)
    else:
        context["loop_overruns"] = int(context.get("loop_overruns", 0)) + 1
    finished = time.monotonic()
    next_deadline = deadline + period
    if next_deadline <= finished:
        next_deadline += (math.floor((finished - next_deadline) / period) + 1) * period
    context["loop_next_deadline"] = next_deadline


class FixedRatePoseStream:
    """[추가] Interpolate retargeted samples onto an exact, bounded 50 Hz grid.

No extrapolation: emit only targets bracketed by received samples. A large input
gap starts a new segment with zero initial velocity instead of inventing motion
through the missing interval. Frame IDs advance across that gap.
    """

    def __init__(self, fps: float = 50.0, num_frames: int = 5, max_gap_s: float = 0.25):
        if not math.isfinite(fps) or fps <= 0 or num_frames < 1 or max_gap_s <= 0:
            raise ValueError("Invalid pose stream timing parameters")
        self.period = 1.0 / fps
        self.num_frames = int(num_frames)
        self.max_gap_s = float(max_gap_s)
        self.history = deque(maxlen=max(self.num_frames, math.ceil(max_gap_s * fps) + 2))
        self.origin = None
        self.previous = None
        self.next_index = 0
        self.total_frames = 0
        self.gap_resets = 0

    @staticmethod
    def _quat(q):
        q = np.asarray(q, dtype=np.float64).reshape(4)
        norm = float(np.linalg.norm(q))
        if not np.all(np.isfinite(q)) or norm < 1e-8:
            raise ValueError("Invalid body quaternion; pose not published")
        return q / norm

    def _append(self, q, quat, index, stamp, *, reset=False):
        velocity = np.zeros(29, dtype=np.float64)
        if self.history and not reset:
            previous = self.history[-1]
            dt = (index - previous["index"]) * self.period
            velocity = (q - previous["q"]) / dt
        self.history.append({"q": q.copy(), "quat": quat.copy(), "v": velocity,
                             "index": int(index), "stamp": float(stamp)})
        self.total_frames += 1
        self.next_index = int(index) + 1

    def push(self, joint_pos, body_quat, timestamp_monotonic, timestamp_realtime,
             *, catch_up=True):
        q = np.asarray(joint_pos, dtype=np.float64).reshape(29)
        quat = self._quat(body_quat)
        t, wall = float(timestamp_monotonic), float(timestamp_realtime)
        if not np.all(np.isfinite(q)) or not math.isfinite(t) or not math.isfinite(wall):
            raise ValueError("Non-finite reference/timestamp; pose not published")
        current = (t, wall, q.copy(), quat)
        produced = 0
        if self.previous is None:
            self.origin = t
            self._append(q, quat, 0, wall, reset=True)
            produced = 1
        else:
            pt, pw, pq, pquat = self.previous
            if t <= pt:
                return None  # Same sensor sample is never relabelled as new motion.
            if t - pt > self.max_gap_s:
                index = max(self.next_index, round((t - self.origin) / self.period))
                self.origin = t - index * self.period
                self.history.clear()
                self._append(q, quat, index, wall, reset=True)
                self.gap_resets += 1
                produced = 1
            else:
                end_index = math.floor((t - self.origin) / self.period + 1e-7)
                # q and -q represent the same rotation; use the shortest arc.
                if float(np.dot(pquat, quat)) < 0:
                    quat = -quat
                for index in range(self.next_index, end_index + 1):
                    target = self.origin + index * self.period
                    alpha = float(np.clip((target - pt) / (t - pt), 0.0, 1.0))
                    use_q = (1.0 - alpha) * pq + alpha * q
                    use_quat = self._quat((1.0 - alpha) * pquat + alpha * quat)
                    stamp = (1.0 - alpha) * pw + alpha * wall
                    self._append(use_q, use_quat, index, stamp)
                    produced += 1
        self.previous = current
        if not produced:
            return None
        # Include all newly interpolated frames after a short processing overrun.
        frames = list(self.history)[-max(self.num_frames, produced):]
        n = len(frames)
        return {
            "joint_pos": np.asarray([f["q"] for f in frames], dtype=np.float32),
            "joint_vel": np.asarray([f["v"] for f in frames], dtype=np.float32),
            "body_quat": np.asarray([f["quat"] for f in frames], dtype=np.float32),
            "frame_index": np.asarray([f["index"] for f in frames], dtype=np.int64),
            "timestamp_realtime": np.asarray([f["stamp"] for f in frames], dtype=np.float64),
            "heading_increment": np.zeros(n, dtype=np.float32),
            "catch_up": np.full(n, bool(catch_up), dtype=bool),
        }


def log_stream_timing(state, *, interval_s=5.0):
    """[추가] Separate input, processing, message rate, and reference-frame rate."""
    ctx = state.context
    now = time.monotonic()
    stats = ctx.setdefault("stream_timing_stats", {"start": now, "loops": 0, "sums": {},
                                                   "rx": 0, "frames": 0, "pubs": 0,
                                                   "overruns": 0})
    stats["loops"] += 1
    for key in ("body_read_ms", "retarget_ms", "loop_work_ms"):
        stats["sums"][key] = stats["sums"].get(key, 0.0) + float(ctx.get(key, 0.0))
    elapsed = now - stats["start"]
    if elapsed < interval_s:
        return
    stream = ctx.get("sonic_fixed_rate_stream")
    rx = int(ctx.get("body_rx_frames", 0))
    frames = stream.total_frames if stream else 0
    pubs = int(ctx.get("sonic_publish_count", 0))
    overruns = int(ctx.get("loop_overruns", 0))
    source_stamp = ctx.get("body_last_received_monotonic")
    age_ms = (now - source_stamp) * 1000.0 if source_stamp is not None else float("nan")
    means = {k: v / stats["loops"] for k, v in stats["sums"].items()}
    print(f"[teleop-timing] loop={stats['loops']/elapsed:.1f}Hz "
          f"rx={(rx-stats['rx'])/elapsed:.1f}Hz "
          f"pub={(pubs-stats['pubs'])/elapsed:.1f}Hz "
          f"frames={(frames-stats['frames'])/elapsed:.1f}Hz "
          f"read={means.get('body_read_ms',0):.2f}ms "
          f"gmr={means.get('retarget_ms',0):.2f}ms "
          f"work={means.get('loop_work_ms',0):.2f}ms "
          f"rx_age={age_ms:.1f}ms overruns={overruns-stats['overruns']} "
          f"gap_resets={stream.gap_resets if stream else 0} "
          f"status={ctx.get('zmq_publish_status','waiting')}", flush=True)
    if age_ms > 250 or (pubs - stats["pubs"]) / elapsed < 40:
        print("[teleop-warning] Stale/slow reference; inspect rx, gmr and work above. "
              "rx_age is host reception age, not sensor capture latency.", flush=True)
    stats.update(start=now, loops=0, sums={}, rx=rx, frames=frames, pubs=pubs, overruns=overruns)
