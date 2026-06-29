# Benchmarks (not unit tests)

Scripts that measure registration quality and speed on real local fixtures.
They are not part of the pytest suite. Run with `uv run python benchmarks/<name>.py`.

Key findings on Lena Knie 19 T0→T1 DESS (24 h patient repositioning):

| Approach | Wall-time | Dice |
|---|---|---|
| affine baseline (no deformable) | <1 s | 0.260 |
| elastix default, 500 iter | ~11-15 s | 0.564 |
| elastix + N4 bias correction | ~15 s | 0.569 |
| elastix + every preprocessing trick | ~20-30 s | 0.567 |
| elastix + 4000 iter (plateau) | ~85 s | 0.569 |
| mask-to-mask ceiling (cheat: needs target mask) | ~15 s | 0.825 |

Take-away: pure intensity-based registration on cross-session DESS-DESS
plateaus around Dice 0.57. The anatomical ceiling is ~0.82. Improvements
beyond 0.60 require either auto-segmentation of bones (cascade approach)
or ML-based registration (VoxelMorph etc.), neither of which is built in.
