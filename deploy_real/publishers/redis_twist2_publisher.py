from __future__ import annotations

import json
import os
from typing import Any, Dict


def publish_twist2_step(
    *,
    redis_client: Any,
    body_35: list[float],
    hand_tracking_left: Dict[str, Any],
    hand_tracking_right: Dict[str, Any],
    wuji_mode_left: str,
    wuji_mode_right: str,
    now_ms: int,
) -> None:
    # [ADDED Xsens sim-only] Isolated key: never publish legacy body/hand keys.
    if os.environ.get("TWIST2_XSENS_SIM_ONLY") == "1":
        if len(body_35) != 35:
            raise ValueError(f"Xsens TWIST2 sim expected 35 floats, got {len(body_35)}")
        redis_client.set("twist2_xsens_sim:reference", json.dumps({
            "timestamp_ms": int(now_ms), "body_35": body_35,
        }), px=500)
        return
    robot_key = "unitree_g1_with_hands"
    key_action_body = f"action_body_{robot_key}"
    key_t_action = "t_action"
    key_ht_l = f"hand_tracking_left_{robot_key}"
    key_ht_r = f"hand_tracking_right_{robot_key}"
    key_wuji_mode_l = f"wuji_hand_mode_left_{robot_key}"
    key_wuji_mode_r = f"wuji_hand_mode_right_{robot_key}"

    pipe = redis_client.pipeline()
    pipe.set(key_action_body, json.dumps(body_35))
    pipe.set(key_ht_l, json.dumps(hand_tracking_left))
    pipe.set(key_ht_r, json.dumps(hand_tracking_right))
    pipe.set(key_wuji_mode_l, wuji_mode_left)
    pipe.set(key_wuji_mode_r, wuji_mode_right)
    pipe.set(key_t_action, int(now_ms))
    pipe.execute()
