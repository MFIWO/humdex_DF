#!/usr/bin/env bash
# [ADDED] Use HumDex Xsens/GMR, publish to isolated Redis key only; no SONIC.
set -euo pipefail
cd "$HOME/robotics/humdex"
export TWIST2_XSENS_SIM_ONLY=1
# [CHANGED] Prefer current activated gmr, otherwise the validated Miniforge gmr.
if [[ "${CONDA_DEFAULT_ENV:-}" == "gmr" && -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
  GMR_PYTHON="${CONDA_PREFIX}/bin/python"
else
  GMR_PYTHON="$HOME/miniforge3/envs/gmr/bin/python"
fi
if ! "$GMR_PYTHON" -c 'import zmq,redis,numpy' 2>/dev/null; then
  echo "[error] Missing dependencies in $GMR_PYTHON (check pyzmq/redis/numpy)" >&2
  exit 1
fi
echo "[twist2-xsens] using $GMR_PYTHON"
exec "$GMR_PYTHON" -m deploy_real.entrypoints.teleop_entry \
  --policy twist2 --body xsens --hand manus -- \
  --config_yaml "$HOME/Downloads/twist2_mjlab-master/deploy/xsens_sim/xsens_body_sim.yaml"
