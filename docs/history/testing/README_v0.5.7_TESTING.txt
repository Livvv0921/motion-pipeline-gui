Motion Pipeline GUI v0.5.7 — release testing notes
=================================================

This is the final pre-GitHub GUI revision built from v0.5.6.3.

Launch
------
conda activate motion-gui
cd <extracted motion_pipeline_gui_v0.5.7 folder>
python launcher.py

What changed most
-----------------
1. Backend jobs are no longer globally serialized. Each RUN action launches its own QProcess, so independent tasks can run concurrently.
2. The console bar shows overall active-job progress; each running sidebar stage gets a temporary local progress bar.
3. Console docking to the right is explicitly restored and now also has DOCK RIGHT / DOCK BOTTOM shortcut buttons.
4. Compare Lab's control column can collapse all the way closed.
5. Peak/Movement Lab collapsible sections start open.
6. Plot palette choices were reduced to three final sets: Coral Grove, Orchid Dusk, Aqua Current.
7. Dark mode is based on #212226. Light mode returns to a white canvas with restrained Coral Grove accents.

Parallel-processing caution
---------------------------
Parallel support means separate backend Python processes run at the same time. It does NOT create extra hardware resources. CPU, RAM, network/disk I/O, and GPU/VRAM are shared.

Good parallel examples:
- Triangulate Trial A while visualizing already-finished Trial B.
- Calibrate a separate calibration recording while reviewing/plotting another completed dataset.
- Run independent jobs that write to different folders.

Avoid:
- Two jobs overwriting the same trial/output files.
- Visualization reading a CSV that another job is actively replacing.
- Multiple heavy DeepLabCut GPU jobs if VRAM is limited.

Progress behavior
-----------------
Backends now print standardized [PROGRESS N%] milestones. Some long external library calls cannot expose internal percentages; during those calls the bar may remain at its most recent milestone until the call finishes. This is expected and more honest than a fake timer.

Qt testing limitation
---------------------
The release was syntax/bytecode checked in the build environment. Full visual Qt/PySide6 behavior must still be click-tested on the workstation where PySide6/QtWebEngine is installed. Use TEST_SHEET_v0.5.7.md for the focused regression sequence.
