# Motion Pipeline GUI v0.5.6.3 — focused test sheet

## 1. Light-mode contrast
- Switch to **Light Mode**.
- Confirm the main background is a warm off-white rather than beige/pale yellow.
- Confirm normal text and subtitle text are easy to read.
- Confirm muted blue is clearly visible in selected navigation/tabs, run buttons,
  panel/section accents, and focus/selection states.
- Open Peak Lab, Movement Lab, and Compare Lab and confirm plots use a near-white
  plotting canvas with readable dark labels/grid lines.

## 2. Peak Lab: one-click Move Mode
1. Load a 3D CSV and find or load some peaks.
2. Manually turn **Hover details** OFF.
3. Click **SELECT / MOVE PEAK** in the plot header.
4. Expected: **Hover details turns back ON automatically**.
5. Click one peak marker.
6. Expected:
   - the matching Event Dataset row becomes selected;
   - its frame appears in Manual Review;
   - the selected peak dot becomes visibly larger;
   - the current graph zoom does not change.

## 3. Manual Review: move selected peak
1. Keep Move Mode on and click a peak marker.
2. Click a different frame on the plot, or type a different frame in Manual Review.
3. Press **MOVE SELECTED PEAK** in Manual Review.
4. Expected: the selected event moves to the destination frame and its time/XYZ
   values update. You should NOT have to click the Event Dataset first.

## 4. Manual Review: remove selected peak
1. Click a peak marker on the plot.
2. Press **REMOVE SELECTED PEAK** in Manual Review.
3. Expected: that selected peak is removed immediately.
4. Repeat by selecting a row in Event Dataset first, then using the same Manual
   Review button. Both paths should work.

## 5. Selected-dot feedback
- Click several different peaks one at a time.
- Expected: the current selected peak is enlarged; previous peaks return to normal.
- Select a row directly in Event Dataset.
- Expected: the matching graph marker enlarges without resetting zoom.

## 6. Regression checks
- Peak detection, range confirmation, save/open review session, CSV/MAT export.
- Peak Lab Overlay / Separate XYZ / Primary trace on top.
- Compare Lab hide/show controls and stacked plot resizing.
- Movement Lab video seek, ±5 s, playback speed, and trace cursor sync.
- Dark mode should look the same as v0.5.6.2 aside from behavior fixes.
