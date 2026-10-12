"""[추가] Isolated tests: synthetic UDP on an ephemeral port, no robot connection."""
import socket
import struct
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from deploy_real.adapters.body.xsens_adapter import XsensBodyConfig, XsensBodyReader
from deploy_real.pipelines.utils.stream_timing import FixedRatePoseStream, sleep_until_next_tick


class PoseStreamTests(unittest.TestCase):
    def sample(self, stream, t, speed=2.0, quat=(1, 0, 0, 0)):
        return stream.push(np.full(29, speed * t), quat, 100.0 + t, 1000.0 + t)

    def test_60hz_to_50hz_preserves_motion_time_and_velocity(self):
        stream = FixedRatePoseStream()
        seen = {}
        for i in range(61):
            payload = self.sample(stream, i / 60.0)
            if payload:
                for j, index in enumerate(payload["frame_index"]):
                    seen[int(index)] = (payload["joint_pos"][j], payload["joint_vel"][j],
                                        payload["timestamp_realtime"][j])
        self.assertEqual(sorted(seen), list(range(51)))
        for index, (q, v, stamp) in seen.items():
            np.testing.assert_allclose(q, 2 * index / 50, atol=1e-6)
            np.testing.assert_allclose(v, 2.0 if index else 0.0, atol=1e-5)
            self.assertAlmostEqual(stamp, 1000 + index / 50, places=7)

    def test_processing_overrun_preserves_all_grid_frames(self):
        stream = FixedRatePoseStream()
        self.sample(stream, 0.0)
        payload = self.sample(stream, 0.18)
        np.testing.assert_array_equal(payload["frame_index"], np.arange(1, 10))
        np.testing.assert_allclose(payload["joint_vel"], 2.0, atol=1e-6)

    def test_irregular_input_keeps_exact_time_grid(self):
        stream = FixedRatePoseStream()
        for t in [0, .017, .037, .068, .081, .107]:
            payload = self.sample(stream, t)
        np.testing.assert_array_equal(payload["frame_index"], np.arange(1, 6))
        np.testing.assert_allclose(np.diff(payload["timestamp_realtime"]), .02, atol=1e-8)
        np.testing.assert_allclose(payload["joint_vel"], 2.0, atol=1e-5)

    def test_duplicate_and_backward_samples_are_not_republished(self):
        stream = FixedRatePoseStream()
        self.sample(stream, .02)
        self.assertIsNone(self.sample(stream, .02))
        self.assertIsNone(self.sample(stream, .01))
        self.assertEqual(stream.total_frames, 1)

    def test_gap_does_not_invent_motion_or_velocity(self):
        stream = FixedRatePoseStream()
        self.sample(stream, 0)
        self.sample(stream, .02)
        payload = self.sample(stream, .52)
        self.assertEqual(stream.gap_resets, 1)
        np.testing.assert_array_equal(payload["frame_index"], [26])
        np.testing.assert_allclose(payload["joint_vel"], 0)
        self.assertEqual(len(payload["joint_pos"]), 1)

    def test_quaternion_sign_flip_does_not_create_rotation(self):
        stream = FixedRatePoseStream()
        self.sample(stream, 0)
        payload = self.sample(stream, .04, quat=(-1, 0, 0, 0))
        np.testing.assert_allclose(np.abs(payload["body_quat"][:, 0]), 1)
        np.testing.assert_allclose(payload["body_quat"][:, 1:], 0)

    def test_stationary_targets_have_zero_velocity(self):
        stream = FixedRatePoseStream()
        for t in [0, .02, .04]:
            payload = stream.push(np.ones(29), [1, 0, 0, 0], t, 1000 + t)
        np.testing.assert_allclose(payload["joint_vel"], 0)

    def test_invalid_pose_rejected_without_changing_stream(self):
        stream = FixedRatePoseStream()
        with self.assertRaises(ValueError):
            stream.push(np.full(29, np.nan), [1, 0, 0, 0], 0, 1000)
        with self.assertRaises(ValueError):
            stream.push(np.zeros(29), [0, 0, 0, 0], 0, 1000)
        self.assertEqual(stream.total_frames, 0)


class RateLimiterTests(unittest.TestCase):
    def test_7ms_work_sleeps_only_remaining_13ms(self):
        ctx = {"loop_start_monotonic": 10.0}
        with patch("deploy_real.pipelines.utils.stream_timing.time.monotonic", side_effect=[10.007, 10.020]), \
             patch("deploy_real.pipelines.utils.stream_timing.time.sleep") as sleep:
            sleep_until_next_tick(ctx, 50)
        self.assertAlmostEqual(sleep.call_args.args[0], .013)
        self.assertAlmostEqual(ctx["loop_next_deadline"], 10.040)

    def test_overrun_does_not_add_20ms_or_leave_expired_deadline(self):
        ctx = {"loop_start_monotonic": 10.0, "loop_next_deadline": 10.020}
        with patch("deploy_real.pipelines.utils.stream_timing.time.monotonic", side_effect=[10.067, 10.067]), \
             patch("deploy_real.pipelines.utils.stream_timing.time.sleep") as sleep:
            sleep_until_next_tick(ctx, 50)
        sleep.assert_not_called()
        self.assertAlmostEqual(ctx["loop_next_deadline"], 10.080)
        self.assertEqual(ctx["loop_overruns"], 1)


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.reader = XsensBodyReader(XsensBodyConfig(listen_ip="127.0.0.1", listen_port=0,
                                                     socket_timeout_s=.05, quat_order="wxyz"))
        self.reader.initialize()
        self.address = self.reader.sock.getsockname()
        self.sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def tearDown(self):
        self.sender.close()
        self.reader.close()

    def send(self, sample=1, ids=range(1, 24), last=True, part=0):
        ids = list(ids)
        payload = b"".join(struct.pack(">I7f", i, i * .01, 0, 1, 1, 0, 0, 0) for i in ids)
        header = struct.pack(">6sIBBIBBBBHH", b"MXTP02", sample, part | (128 if last else 0),
                             len(ids), sample * 16, 0, 23, 0, 0, 0, len(payload))
        self.sender.sendto(header + payload, self.address)

    def wait_frame(self):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            out = self.reader.read_frame()
            if out.get("ok"):
                return out
            time.sleep(.001)
        self.fail("No complete synthetic UDP frame")

    def test_empty_read_never_waits_for_socket_timeout(self):
        start = time.perf_counter()
        for _ in range(10):
            self.assertFalse(self.reader.read_frame()["ok"])
        self.assertLess(time.perf_counter() - start, .025)

    def test_complete_sample_has_original_receipt_time_and_no_duplicates(self):
        before = time.monotonic()
        self.send()
        out = self.wait_frame()
        self.assertGreaterEqual(out["timestamp_monotonic"], before)
        self.assertLessEqual(out["timestamp_monotonic"], time.monotonic())
        self.assertEqual(out["source_time_code"], 16)
        self.assertEqual(len(out["body_frame"]), 23)
        self.assertFalse(self.reader.read_frame()["ok"])

    def test_split_datagram_waits_for_complete_sample(self):
        self.send(ids=range(1, 12), last=False)
        time.sleep(.01)
        self.assertFalse(self.reader.read_frame()["ok"])
        self.send(ids=range(12, 24), last=True, part=1)
        self.assertEqual(len(self.wait_frame()["body_frame"]), 23)

    def test_burst_returns_latest_complete_sample(self):
        for sample in range(1, 11):
            self.send(sample=sample)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            with self.reader._lock:
                if self.reader._rx_sequence == 10:
                    break
            time.sleep(.001)
        out = self.reader.read_frame()
        self.assertEqual(out["frame_index"], 10)
        self.assertEqual(out["rx_frames_total"], 10)

    def test_second_receiver_cannot_steal_udp_port(self):
        second = XsensBodyReader(XsensBodyConfig(listen_ip="127.0.0.1", listen_port=self.address[1]))
        try:
            with self.assertRaises(OSError):
                second.initialize()
        finally:
            second.close()


if __name__ == "__main__":
    unittest.main()
