#!/usr/bin/env bash
# [ADDED] Only MuJoCo + policy; isolated Xsens bridge in separate terminal.
# Do not use deploy/play_real_twist2.sh for live inputs.
set -euo pipefail
cd "$HOME/Downloads/twist2_mjlab-master"
MODEL="${1:-$PWD/resources/pretrained_seed.onnx}"
[[ -f "$MODEL" ]] || { echo "Missing checkpoint: $MODEL" >&2; exit 1; }
export PYTHONPATH="$PWD:$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
# [ADDED] Applies only to this Xsens simulation launcher.
export TWIST2_XSENS_SIM_GATE=1
if ss -lunH | grep -Eq ':(9880|9881|9892|9893)[[:space:]]'; then
  echo 'ERROR: TWIST2 SIM UDP ports 9880/9881/9892/9893 already in use' >&2
  exit 1
fi
# [CHANGED] Launch both nodes in background; D-terminal owns manual keys.
policy_pid=''
sim_pid=''
cleanup() {
  trap - EXIT INT TERM
  [[ -z "$sim_pid" ]] || { kill "$sim_pid" 2>/dev/null || true; wait "$sim_pid" 2>/dev/null || true; }
  [[ -z "$policy_pid" ]] || { kill "$policy_pid" 2>/dev/null || true; wait "$policy_pid" 2>/dev/null || true; }
}
trap cleanup EXIT INT TERM
uv run --no-sync python deploy/policy/twist2_policy.py "$MODEL" --live-mimic-port 9892 &
policy_pid=$!
sleep 2
kill -0 "$policy_pid" 2>/dev/null || { echo 'Policy failed to start' >&2; exit 1; }
uv run --no-sync python deploy/sim/sim_node.py &
sim_pid=$!
sleep 2
kill -0 "$sim_pid" 2>/dev/null || { echo 'MuJoCo sim failed to start' >&2; exit 1; }
# [CHANGED] Operator input. Ctrl+C terminates both nodes; does not affect SONIC.
uv run --no-sync python deploy/xsens_sim/keyboard_control.py
