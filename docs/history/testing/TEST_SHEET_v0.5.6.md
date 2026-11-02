# Motion Pipeline GUI v0.5.6 — Test Sheet

> Use this after extracting v0.5.6. The detailed expected behavior is also in `README_v0.5.6_TESTING.txt`.

- [ ] **1. Triangulation trial-folder guard**
- [ ] **2. Triangulation threshold step**
- [ ] **3. Movable console / triangulation layout**
- [ ] **4. Light theme + palettes**
- [ ] **5. Peak Lab trace layouts**
- [ ] **6. Peak Lab zoom persistence**
- [ ] **7. Manual Review move/remove controls**
- [ ] **8. Peak/timepoint velocity**
- [ ] **9. Peak Lab save/reopen review session**
- [ ] **10. Movement Lab automatic video match**
- [ ] **11. Movement Lab Video Inspector**
- [ ] **12. Compare Lab layouts / palette / export**
- [ ] **13. Context/status sanity check**
- [ ] **14. Regression smoke test**

## Release-critical checks

- [ ] Triangulation rejects selecting the `3d` subfolder and threshold arrows step by 0.1.
- [ ] Bottom console remains movable without covering the Triangulation run controls.
- [ ] Light mode uses the new lavender/plum/teal theme and all shared palettes remain readable.
- [ ] Peak Lab Overlay / Separate XYZ / Primary trace on top all render.
- [ ] Peak selection, move, and remove preserve the current zoom.
- [ ] Manual Review MOVE and REMOVE controls act on the same selected Event Dataset rows.
- [ ] Exported Peak CSV/MAT rows include `velocity_3d`.
- [ ] Peak review session saves/reopens, including zoom/layout/palette and labeled events.
- [ ] Movement Lab auto-matches the raw-video folder when possible.
- [ ] Video scrub, ±5 s, and playback speed keep the trace cursor synchronized.
- [ ] Compare Lab exports PNG, SVG, PDF, and interactive HTML.
- [ ] Regression smoke tests for Passive / Calibration / Triangulation / Visualization still pass.
