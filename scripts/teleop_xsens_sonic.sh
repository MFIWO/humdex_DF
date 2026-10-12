#!/usr/bin/env bash
# [추가] Explicit body-only configuration and preflight; no hardware is started by --check-only.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--check-only" ) ]]; then
  echo "Usage: bash scripts/teleop_xsens_sonic.sh [--check-only]" >&2
  exit 2
fi
CONFIG="deploy_real/config/teleop_xsens_body.yaml"
if [[ ! -f "${CONFIG}" ]]; then
  echo "[error] Missing body-only config: ${REPO_ROOT}/${CONFIG}" >&2
  exit 1
fi
python -m unittest discover -s tests -p test_xsens_stream_timing.py -q
python - "${CONFIG}" <<'PY'
import sys
from pathlib import Path
from deploy_real.pipelines.utils.config import load_sonic_runtime_config
from deploy_real.pipelines.utils import stages  # Check real environment imports before opening sockets.
cfg = load_sonic_runtime_config(passthrough=["--config_yaml", sys.argv[1]], repo_root=Path.cwd())
if abs(cfg.target_fps - 50.0) > 1e-6 or cfg.zmq_frame_index_step != 1:
    raise SystemExit("[error] Xsens/SONIC needs target_fps=50 and zmq_frame_index_step=1")
print(f"[preflight] fps={cfg.target_fps} height={cfg.actual_human_height}m hands={cfg.hands} "
      f"UDP={cfg.xsens_listen_ip}:{cfg.xsens_listen_port} ZMQ={cfg.zmq_pose_port}")
PY
if [[ "${1:-}" == "--check-only" ]]; then
  echo "[preflight] Passed. No teleop receiver or publisher was started."
  exit 0
fi
echo "[xsens-sonic] config=${REPO_ROOT}/${CONFIG}"
exec bash scripts/teleop.sh --policy sonic --body xsens --hand manus -- --config_yaml "${CONFIG}"
