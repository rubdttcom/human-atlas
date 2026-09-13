"""Synthetic tests of scripts/cryo_metrics.py (the frozen pilot metrics), required by the acceptance protocol before any
evaluation: identical masks, a known shift, the gap between two runs, ignore-adjacent caps, an excluded slice inside a
run, empty prediction, false positives in a run without reference, Dice under an eligibility mask, tolerance and ties,
and the audit counterexample (an eroded prediction improves when dilated: the evaluator is right, the model is wrong).

  .venv/bin/python scripts/test-cryo-metrics.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cryo_metrics as M  # noqa: E402

K0 = 100
results = {}


def box(shape, i, j, k):
    m = np.zeros(shape, bool)
    m[i[0]:i[1], j[0]:j[1], k[0]:k[1]] = True
    return m


def case(name, ok):
    results[name] = bool(ok)
    if not ok:
        print('FAILED', name)


shape = (60, 50, 40)                      # (i, j, K); k = K0 .. K0 + 39
E = np.ones(shape, bool)
runs_one = [(K0, K0 + 39)]
ref = box(shape, (5, 25), (15, 35), (5, 35))            # off-centre in i so the mirror control changes it

# 1. identical
s = M.surface_p95(ref, ref, E, runs_one, K0)
case('identical_dice_1', M.dice(ref, ref, E) == 1.0)
case('identical_p95_0', s['status'] == 'ok' and s['p95_mm'] == 0.0)

# 2. shift by 1 voxel in i -> p95 = 0.666 exactly (every surface voxel moves one pixel; caps at the volume boundary removed)
pred = M.shift_i(ref, 1)
s = M.surface_p95(pred, ref, E, runs_one, K0)
case('shift_1px_p95_0.666', abs(s['p95_mm'] - 0.666) < 1e-9)
case('shift_1px_dice_below_1', M.dice(pred, ref, E) < 1.0)

# 3. two runs separated by a gap: an object only in run A of the reference and, in the prediction, the same object plus a
#    copy 30 voxels away in i inside run B. If runs were concatenated the copy would find the reference 0.333 mm away in k.
E2 = np.ones((60, 50, 40), bool)
runs_two = [(K0, K0 + 9), (K0 + 30, K0 + 39)]                  # k 100..109 and 130..139 (gap 110..129 not eligible)
E2[:, :, 10:30] = False
refA = box(E2.shape, (5, 15), (10, 20), (0, 10))               # run A only
predA = refA.copy(); predA[35:45, 10:20, 30:40] = True         # false positives in run B, 30 voxels away in i
s = M.surface_p95(predA, refA, E2, runs_two, K0)
case('gap_run_without_reference_left_out', s['status'] == 'ok' and s['p95_mm'] == 0.0 and s['per_run'][1]['status'] == 'false-positives-only')
case('gap_fp_counted_in_dice', M.dice(predA, refA, E2) < 1.0)
# the reverse: reference in run B too, prediction misses it -> undefined p95 (fails), not silently pooled
refAB = refA.copy(); refAB[35:45, 10:20, 30:40] = True
s = M.surface_p95(refA, refAB, E2, runs_two, K0)
case('gap_missing_run_is_empty_prediction_in_run', s['status'] == 'empty-prediction-in-run' and s['p95_mm'] is None)

# 4. ignore-adjacent caps: the reference object crosses an ignore region; the prediction equals the reference outside it.
#    Without cap removal the cut faces would produce zero distances (fine) but a prediction that ALSO differs at the cut
#    would be measured on the crop. Test: prediction = reference shifted 1 px in i only inside the ignore region -> p95 0.
E3 = np.ones(shape, bool); E3[:, :, 15:20] = False              # ignore slab (whole slices, like an excluded slice)
pred3 = ref.copy()
pred3[:, :, 15:20] = M.shift_i(ref, 1)[:, :, 15:20]
s = M.surface_p95(pred3, ref, E3, runs_one, K0)
case('ignore_slices_do_not_score', s['p95_mm'] == 0.0 and M.dice(pred3, ref, E3) == 1.0)
#    in-plane ignore block touching the object: the prediction differs only under the ignore block -> no distance
E4 = np.ones(shape, bool); E4[10:20, 20:30, :] = False
pred4 = ref.copy(); pred4[10:20, 20:30, :] = False
s = M.surface_p95(pred4, ref, E4, runs_one, K0)
case('inplane_ignore_caps_removed', s['p95_mm'] == 0.0 and M.dice(pred4, ref, E4) == 1.0)

# 5. empty prediction / empty reference
s = M.surface_p95(np.zeros(shape, bool), ref, E, runs_one, K0)
case('empty_prediction_status', s['status'] == 'empty-prediction' and s['p95_mm'] is None)
s = M.surface_p95(ref, np.zeros(shape, bool), E, runs_one, K0)
case('no_reference_status', s['status'] == 'no-reference')
case('dice_none_when_both_empty', M.dice(np.zeros(shape, bool), np.zeros(shape, bool), E) is None)

# 6. Dice ignores ineligible voxels
pred6 = ref.copy(); pred6[0:5, 0:5, :] = True                    # false positives ...
E6 = np.ones(shape, bool); E6[0:5, 0:5, :] = False              # ... under ignore
case('dice_ignores_ineligible', M.dice(pred6, ref, E6) == 1.0 and M.dice(pred6, ref, E) < 1.0)

# 7. tolerance and ties
base = {'dice': 0.95, 'p95_mm': 1.0}
case('degrades_tolerance', M.degrades(base, {'dice': 0.945, 'p95_mm': 1.2}) == {'dice': False, 'p95': False}
     and M.degrades(base, {'dice': 0.94, 'p95_mm': 1.333}) == {'dice': True, 'p95': True}
     and M.degrades(base, {'dice': 0.5, 'p95_mm': None}) == {'dice': True, 'p95': True})

# 8. audit counterexample: an eroded prediction improves when dilated; the evaluator must report that faithfully
eroded = M.erode_inplane(ref, 3)
d_er = M.dice(eroded, ref, E); d_dil = M.dice(M.dilate_inplane(eroded, 3), ref, E)
case('eroded_prediction_improves_with_dilation', d_er < d_dil <= 1.0)
# and the reference itself must degrade under every control (evaluator sanity direction)
for name, pert in (('mirror', M.mirror_i(ref)), ('shift', M.shift_i(ref, 3)), ('dilation', M.dilate_inplane(ref, 3))):
    b = {'dice': 1.0, 'p95_mm': 0.0}
    p = {'dice': M.dice(pert, ref, E), 'p95_mm': M.surface_p95(pert, ref, E, runs_one, K0)['p95_mm']}
    case(f'reference_degrades_under_{name}', M.degrades(b, p) == {'dice': True, 'p95': True})

# 9. anisotropy: a 1-slice shift in k gives 0.333 mm, not 0.666
predk = np.zeros(shape, bool); predk[:, :, 1:] = ref[:, :, :-1]
s = M.surface_p95(predk, ref, E, runs_one, K0)
case('k_shift_uses_0.333', abs(s['p95_mm'] - 0.333) < 1e-9)

# 11. Codex audit of 8a5da4b: caps must not act as targets. Reference fills the whole eligible run (every reference surface
#     voxel is a cap), prediction is a box inside: no observable reference surface -> undefined, never a finite distance.
shp = (35, 35, 3); Eall = np.ones(shp, bool)
Rall = np.ones(shp, bool); Pbox = np.zeros(shp, bool); Pbox[10:25, 10:25, :] = True
s = M.surface_p95(Pbox, Rall, Eall, [(K0, K0 + 2)], K0)
case('cap_never_a_target', s['status'] == 'no-observable-surface' and s['p95_mm'] is None)
#     nested boxes touching a crop: the prediction's distance must be to the real reference boundary, not to a cap face
shp2 = (40, 40, 12); E2b = np.ones(shp2, bool)
Rn = box(shp2, (5, 35), (5, 35), (0, 12))                     # reference spans the whole k range: its k faces are caps
Pn = box(shp2, (10, 30), (10, 30), (0, 12))                    # prediction 5 px inside: real distance 5 * 0.666 = 3.33 mm
s = M.surface_p95(Pn, Rn, E2b, [(K0, K0 + 11)], K0)
case('nested_box_distance_is_to_real_boundary', s['status'] == 'ok' and s['mean_mm'] >= 3.33 - 1e-9 and 3.33 - 1e-9 <= s['p95_mm'] <= 5 * np.sqrt(2) * 0.666 + 1e-9)   # every distance >= 5 px (a cap target would give 0.333); corners up to 5 sqrt 2 px
case('support_reported', s['support']['reference_surface_caps_removed'] > 0 and s['support']['prediction_surface_kept'] > 0)

# 12. Codex audit of 8a5da4b: a missing prediction in a single-slice run (every reference surface voxel would be a cap)
#     must be detected as emptiness BEFORE cap extraction
shp3 = (30, 30, 9); E3b = np.ones(shp3, bool)
R3 = np.zeros(shp3, bool); R3[5:15, 5:15, 0] = True; R3[5:15, 5:15, 3:9] = True
P3 = np.zeros(shp3, bool); P3[5:15, 5:15, 3:9] = True             # first run omitted entirely
s = M.surface_p95(P3, R3, E3b, [(K0, K0), (K0 + 3, K0 + 8)], K0)
case('missing_single_slice_run_detected', s['status'] == 'empty-prediction-in-run' and s['p95_mm'] is None and s['per_run'][0]['status'] == 'empty-prediction-in-run')

# 13. documented limit: a small omitted component inside a run with a correctly predicted component is NOT emptiness
R4 = box(shape, (5, 25), (15, 35), (5, 35)); R4[40:44, 40:44, 10:12] = True
P4 = box(shape, (5, 25), (15, 35), (5, 35))
s = M.surface_p95(P4, R4, E, runs_one, K0)
case('small_omitted_component_is_a_documented_limit', s['status'] == 'ok' and s['p95_mm'] is not None and M.dice(P4, R4, E) < 1.0)

# 10. k_runs
case('k_runs', M.k_runs([5, 6, 7, 10, 11, 20]) == [(5, 7), (10, 11), (20, 20)])

ok = all(results.values())
print(json.dumps({'cases': len(results), 'all_as_expected': ok, 'failed': [k for k, v in results.items() if not v]}))
sys.exit(0 if ok else 1)
