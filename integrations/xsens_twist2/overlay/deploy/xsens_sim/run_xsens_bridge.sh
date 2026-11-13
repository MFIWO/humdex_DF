#!/usr/bin/env bash
# [ADDED] No G1 hardware connections, sends localhost UDP only.
set -euo pipefail
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
exec "$GMR_PYTHON" \
 "$HOME/Downloads/twist2_mjlab-master/deploy/xsens_sim/redis_to_udp.py" "$@"
