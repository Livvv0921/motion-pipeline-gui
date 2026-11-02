# Motion Pipeline GUI v0.5.7 — focused test sheet

Use your normal Windows workstation / `motion-gui` environment. The code was statically checked here, but Qt/PySide6 cannot be visually launched in the build environment.

## A. Parallel backend jobs

- [ ] Start one backend job (for example Triangulation on Trial A).
- [ ] Without waiting for it to finish, switch pages and start a second independent job (for example Visualization on Trial B).
- [ ] Confirm both continue running at the same time.
- [ ] Confirm console lines are tagged by job/stage rather than mixing anonymously.
- [ ] Confirm the console header says `RUNNING: 2 TASKS`.
- [ ] Confirm the overall console progress bar updates as jobs advance.
- [ ] Confirm each active sidebar stage shows a small progress bar.
- [ ] Confirm a stage's small progress bar disappears when that stage has no active job.
- [ ] Try two jobs from the same stage using DIFFERENT output folders; confirm the stage remains `running` until both finish.
- [ ] Test STOP ALL RUNNING with two active jobs.

**Safety:** do not deliberately run two jobs that overwrite the same files. If testing two DLC/Passive jobs, watch GPU VRAM usage.

## B. Console docking

- [ ] Show the Console.
- [ ] Drag its title bar from bottom to the right side.
- [ ] Confirm it docks vertically on the right and the central page resizes.
- [ ] Click `DOCK BOTTOM`, then `DOCK RIGHT`.
- [ ] Float it and dock it again.

## C. Compare Lab controls

- [ ] Open Compare Lab.
- [ ] Drag the left/right splitter until the control panel fully collapses.
- [ ] Restore it by dragging the splitter back.
- [ ] Test `HIDE CONTROLS` / `SHOW CONTROLS` as well.
- [ ] Confirm the plot expands into the released space without a permanent blank column.

## D. Peak / Movement Lab open state

On first opening each page:

- [ ] Peak Lab: SIGNAL / VIEW is open.
- [ ] Peak Lab: SIGNAL CLEANUP is open.
- [ ] Peak Lab: WORKING RANGE is open.
- [ ] Peak Lab: FIND PEAKS is open.
- [ ] Peak Lab: MANUAL REVIEW is open.
- [ ] Movement Lab: SIGNAL / VIEW is open.
- [ ] Movement Lab: MOVEMENT PROTOCOL is open.
- [ ] Movement Lab: MOVEMENT WINDOW is open.
- [ ] Movement Lab: LABEL MOVEMENT is open.
- [ ] Movement Lab: VIDEO INSPECTION is open.

## E. Palette cleanup

Peak Lab and Compare Lab should show exactly three trace palettes:

- [ ] `Coral Grove — Rose / Peach / Sage`
- [ ] `Orchid Dusk — Indigo / Violet / Pink`
- [ ] `Aqua Current — Cobalt / Cyan / Mint`
- [ ] Confirm no old Classic / Plum / Electric / Neon / Forest palette choices remain.

## F. Dark theme

- [ ] Main background visually matches the reference-image dark canvas (`#212226`).
- [ ] Peak/Compare plot canvas uses the same dark background family.
- [ ] Purple/pink controls remain readable and do not disappear into the background.
- [ ] Movement Lab traces are bright enough on dark mode.

## G. Light theme

- [ ] Main background is white / close to the ChatGPT-style white canvas rather than beige or pink.
- [ ] Text has strong dark contrast.
- [ ] Buttons use restrained rose/peach/sage accents instead of coating the whole GUI in color.
- [ ] Inputs/tables remain easy to distinguish from the white page.
- [ ] All three plotting palettes remain distinguishable on white.

## H. Regression checks

- [ ] Peak Lab Move Mode still auto-enables Hover Details.
- [ ] Clicking a selected peak visibly enlarges/highlights its marker.
- [ ] Manual Review MOVE SELECTED PEAK works from the shared selected event.
- [ ] Manual Review REMOVE SELECTED PEAK works without using Event Dataset REMOVE SELECTED.
- [ ] Current Peak Lab zoom is preserved across selection/move/remove.
- [ ] Movement Lab exact raw-video matching still rejects a wrong recording timestamp.
- [ ] Triangulation still protects existing 3D files when overwrite is off.
- [ ] Auto camera count still falls back safely if a TOML structure is unusual.

## Report back

If anything is wrong, the most useful report is: **page + control + what you clicked + what happened + console text (if any)**. A screenshot is especially helpful for layout/theme issues.
