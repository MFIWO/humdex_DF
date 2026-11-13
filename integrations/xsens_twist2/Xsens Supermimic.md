#Xsens-Supermimic

##Terminal A — Xsens MVN Studio
sudo usermod -aG dialout "$(id -un)"

# [추가] 현재 터미널에 새 그룹 적용
newgrp dialout

# [진단] 권한 확인 후 같은 터미널에서 MVN 실행
env \
  __NV_PRIME_RENDER_OFFLOAD=1 \
  __VK_LAYER_NV_optimus=NVIDIA_only \
  __GLX_VENDOR_LIBRARY_NAME=nvidia \
  "$HOME/Applications/Xsens/MVN-Studio-2026.9.appimage" \
  2>&1 | tee "$HOME/Desktop/xsens_nvidia_test.log"
  
##Terminal B — Xsens → GMR
conda activate gmr
cd ~/Downloads/twist2_mjlab-master

bash deploy/xsens_sim/run_xsens_source.sh

##Terminal C — Xsens 참조 모션 Bridge
cd ~/Downloads/twist2_mjlab-master

bash deploy/xsens_sim/run_xsens_bridge.sh

##Terminal D — TWIST2 MuJoCo 시뮬레이션
cd ~/Downloads/twist2_mjlab-master

bash deploy/xsens_sim/run_xsens_sim.sh
