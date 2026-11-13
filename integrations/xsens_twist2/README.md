# Xsens Supermimic / TWIST2 simulation

Snapshot of the local Xsens integration used on 2026-11-13.
Original terminal commands: [Xsens Supermimic.md](Xsens%20Supermimic.md).

## Restore

This overlay requires an existing TWIST2 MJLab installation. It includes Xsens
launchers, configuration, Redis/UDP bridge, keyboard controller, and the policy and
simulator files they require. The HumDex Redis publisher change is in this repo.

Required paths and dependencies:

- Clone MFIWO/humdex_DF at `$HOME/robotics/humdex`, with HumDex/GMR dependencies.
- Existing TWIST2 installation at `$HOME/Downloads/twist2_mjlab-master`, including
  its source, robot assets, uv environment (MuJoCo, MJLab, ONNX), and
  `resources/pretrained_seed.onnx`. These are not bundled in this overlay.
- Activated gmr conda environment, or `$HOME/miniforge3/envs/gmr/bin/python`.
- Redis running on localhost:6379.

From this repository root, copy the overlay onto TWIST2. This overwrites the
corresponding files; preserve any other local modifications first.

```bash
cp -a integrations/xsens_twist2/overlay/. "$HOME/Downloads/twist2_mjlab-master/"
```

## Run

Start MVN Studio with the original command document and stream to localhost:9763.
The configuration uses height 1.75 m and no hands; adjust xsens_body_sim.yaml as needed.
Run each block in a separate terminal:

```bash
# B: Xsens -> GMR -> Redis
conda activate gmr
cd "$HOME/Downloads/twist2_mjlab-master"
bash deploy/xsens_sim/run_xsens_source.sh
```

```bash
# C: Redis -> localhost UDP
cd "$HOME/Downloads/twist2_mjlab-master"
bash deploy/xsens_sim/run_xsens_bridge.sh
```

```bash
# D: policy and MuJoCo
cd "$HOME/Downloads/twist2_mjlab-master"
bash deploy/xsens_sim/run_xsens_sim.sh
```

In D, press `]` then Enter to arm and enable tracking with a fresh reference.
Use the source terminal's `k` send toggle if reference publishing is disabled.
Ctrl+C in D stops its policy and simulator. Launchers opt into simulation-only
Redis publishing and localhost UDP transport.

## Validation

Python parsing, launcher shell syntax, and publisher opt-in/legacy behavior were
checked before upload. Live Xsens and MuJoCo were not exercised during this upload.
