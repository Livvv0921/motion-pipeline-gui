v0.5.2 Compare Lab update

Changes
- Added a third Compare Lab plot mode: Compact stacked (Anipose-style).
- Existing Stacked vertically mode renamed Stacked subplots and kept as an option.
- Added Show hover details toggle.
- Strengthened the blue/coral/pink comparison gradient.
- Export now writes the full Plotly figure as PNG instead of taking a screenshot of the visible widget.
  This requires kaleido in the GUI environment.
- requirements-gui.txt now includes kaleido>=0.2.1.

If PNG export says kaleido is missing:
  pip install kaleido

Suggested test
1. Launch the GUI from motion-gui.
2. In Compare Lab, add several traces from different dates.
3. Try:
   - Overlay
   - Stacked subplots
   - Compact stacked (Anipose-style)
4. Toggle Show trace labels / legend and Show hover details.
5. Export a PNG and confirm that the full plot is saved rather than a screenshot of the viewport.
