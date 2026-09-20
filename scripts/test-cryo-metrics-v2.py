"""Synthetic checks of scripts/cryo_metrics_v2.py (acceptance protocol version 2), next to scripts/cryo_metrics.py (v1)
where the two must agree. Each case builds a small block with labelled structures, an ignore region and a prediction,
and states what the metric must report. Prints one JSON line; exit 1 on any failure.

  .venv/bin/python scripts/test-cryo-metrics-v2.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cryo_metrics as V1  # noqa: E402
import cryo_metrics_v2 as M  # noqa: E402

K0 = 1000
IGN = 255
BONE, CART, MUSCLE = 1, 2, 3
CROSS = np.array([[[0], [1], [0]], [[1], [1], [1]], [[0], [1], [0]]], bool)
results = []


def block(shape=(60, 60, 30)):
    return np.full(shape, IGN, np.uint8)


def box(vol, i0, i1, j0, j1, k0, k1, val):
    vol[i0:i1, j0:j1, k0:k1] = val


def score(ref, pred, cval, runs=None):
    runs = runs or [(K0, K0 + ref.shape[2] - 1)]
    E = ref != IGN
    R, P = ref == cval, pred == cval
    return M.surface_p95(P, R, E, runs, K0), V1.surface_p95(P & E, R & E, E, runs, K0), M.dice(P, R, E), V1.dice(P & E, R & E, E)


def within(v, lo, hi):
    return v is not None and lo <= v <= hi


def case(name, ok, detail=None):
    results.append({'case': name, 'ok': bool(ok), 'detail': detail})


# 1 identity on a fully labelled block: 0 under both, Dice 1
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, MUSCLE); box(ref, 20, 40, 20, 40, 5, 25, BONE)
m, v, d, dv = score(ref, ref.copy(), BONE)
case('identity fully labelled', m['p95_mm'] == 0 and v['p95_mm'] == 0 and d == 1.0 and dv == 1.0, (m['p95_mm'], v['p95_mm']))

# 2 one-pixel erosion, fully labelled: both 0.666; Dice equal between versions
pred = ref.copy(); eroded = ndimage.binary_erosion(ref == BONE, CROSS); pred[(ref == BONE) & ~eroded] = MUSCLE
m, v, d, dv = score(ref, pred, BONE)
case('1 px under-segmentation fully labelled', within(m['p95_mm'], 0.6, 0.7) and within(v['p95_mm'], 0.6, 0.7) and d == dv, (m['p95_mm'], v['p95_mm'], d, dv))

# 3 the v1 artefact: bone surrounded by ignore, a labelled muscle patch touching it, 3 px rim predicted as muscle.
ref = block(); box(ref, 20, 40, 20, 40, 5, 25, BONE); box(ref, 40, 45, 25, 30, 10, 12, MUSCLE)
pred = ref.copy(); core = ndimage.binary_erosion(ref == BONE, CROSS, iterations=3); pred[(ref == BONE) & ~core] = MUSCLE; pred[ref == IGN] = 0
m, v, d, dv = score(ref, pred, BONE)
case('3 px rim missed, bone surrounded by ignore: v2 measures the rim', within(m['p95_mm'], 1.9, 2.1) and v['p95_mm'] > 5.0, (m['p95_mm'], v['p95_mm']))

# 4 the muscle side of a missed bone rim: labelled bone in a labelled background, labelled muscle 20 px away; the 3 px rim
#    of bone predicted as muscle is a bone error (case 3) and must NOT be measured as a muscle boundary 13 mm from the muscle
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, 0); box(ref, 5, 25, 20, 40, 5, 25, BONE); box(ref, 45, 55, 20, 40, 5, 25, MUSCLE)
pred = ref.copy(); core = ndimage.binary_erosion(ref == BONE, CROSS, iterations=3); pred[(ref == BONE) & ~core] = MUSCLE
mm, vm, dm, dvm = score(ref, pred, MUSCLE)
mb, vb, db, dvb = score(ref, pred, BONE)
case('muscle rim inside labelled bone attributed to bone, not muscle',
     mm['status'] == 'ok' and mm['p95_mm'] == 0.0 and mm['support']['prediction_surface_attributed'] < mm['support']['prediction_surface_observable'] and within(mb['p95_mm'], 1.9, 2.5),
     (mm['p95_mm'], mb['p95_mm'], mm['support']))

# 5 a real muscle boundary error is still measured: muscle patch under-segmented by 2 px where the reference has muscle across
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, 0); box(ref, 10, 50, 10, 50, 5, 25, MUSCLE); box(ref, 25, 35, 25, 35, 8, 22, BONE)
pred = ref.copy(); er = ndimage.binary_erosion(ref == MUSCLE, CROSS, iterations=2); pred[(ref == MUSCLE) & ~er] = 0
m, v, d, dv = score(ref, pred, MUSCLE)
case('2 px muscle under-segmentation against background measured', within(m['p95_mm'], 1.3, 1.4) and within(v['p95_mm'], 1.3, 1.4), (m['p95_mm'], v['p95_mm']))

# 6 prediction extends a class 5 px into ignore: not measured, counted
ref = block(); box(ref, 20, 40, 20, 40, 5, 25, BONE); box(ref, 40, 45, 25, 30, 10, 12, MUSCLE)
pred = ref.copy(); pred[ref == IGN] = 0; box(pred, 20, 40, 15, 20, 5, 25, BONE)
m, v, d, dv = score(ref, pred, BONE)
case('extension into ignore counted, not measured', m['p95_mm'] == 0 and m['support']['prediction_surface_against_ignore'] > 0, (m['p95_mm'], m['support']['prediction_surface_against_ignore']))

# 7 shift by 3 px, fully labelled: 1.998 under both; degrades from identity
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, MUSCLE); box(ref, 20, 40, 20, 40, 5, 25, BONE)
E = ref != IGN; R = ref == BONE
m = M.surface_p95(M.shift_i(R, 3), R, E, [(K0, K0 + 29)], K0)
case('3 px shift degrades', within(m['p95_mm'], 1.9, 2.1) and M.degrades({'p95_mm': 0.0}, m)['p95'] is True, m['p95_mm'])

# 8 identity through both k faces is not penalised by the crop
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, MUSCLE); box(ref, 20, 40, 20, 40, 0, 30, BONE)
m, v, d, dv = score(ref, ref.copy(), BONE)
case('faces removed', m['p95_mm'] == 0, m['p95_mm'])

# 9 two runs with a gap: distances never cross the gap
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, MUSCLE); box(ref, 20, 40, 20, 40, 0, 10, BONE); box(ref, 30, 50, 30, 50, 20, 30, BONE)
pred = ref.copy()
m = M.surface_p95(pred == BONE, ref == BONE, ref != IGN, [(K0, K0 + 9), (K0 + 20, K0 + 29)], K0)
case('two runs, identity', m['p95_mm'] == 0 and len(m['per_run']) == 2, m['p95_mm'])

# 10 empty prediction where the reference exists: undefined, fails
m, v, d, dv = score(ref, np.zeros_like(ref), BONE)
case('empty prediction', m['status'] == 'empty-prediction' and v['status'] == 'empty-prediction' and m['p95_mm'] is None, m['status'])

# 11 false positives in a run without reference: left out, reported
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, MUSCLE)
pred = ref.copy(); box(pred, 20, 30, 20, 30, 5, 10, CART)
m, v, d, dv = score(ref, pred, CART)
case('false positives only', m['status'] == 'no-reference' and m['per_run'][0]['status'] == 'false-positives-only' and m['per_run'][0]['n_prediction_voxels'] == 500, m['per_run'][0])

# 12 excluded slice inside a run (ineligible everywhere): no pseudo-boundary, identity still 0
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, MUSCLE); box(ref, 20, 40, 20, 40, 5, 25, BONE)
E = ref != IGN; E[:, :, 15] = False
m = M.surface_p95(ref == BONE, ref == BONE, E, [(K0, K0 + 29)], K0)
case('excluded slice inside a run', m['p95_mm'] == 0, m['p95_mm'])

# 13 anisotropy: a 3-slice k offset is 1 mm, not 3
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, MUSCLE); box(ref, 20, 40, 20, 40, 5, 25, BONE)
R = ref == BONE; P = np.zeros_like(R); P[:, :, 3:] = R[:, :, :-3]
m = M.surface_p95(P, R, ref != IGN, [(K0, K0 + 29)], K0)
case('anisotropic spacing', within(m['p95_mm'], 0.99, 1.01), m['p95_mm'])

# 14 volume on ignore counts only scoring slices
ref = block(); box(ref, 20, 40, 20, 40, 5, 25, BONE)
pred = np.zeros_like(ref); box(pred, 0, 60, 0, 60, 0, 30, CART)
se = np.zeros(30, bool); se[10:20] = True
n = M.volume_on_ignore(pred == CART, ref == IGN, se)
case('volume on ignore', n == 10 * (60 * 60 - 20 * 20), n)

# 15 required neighbour: cartilage 3 px from bone -> median 1.998; not predicted -> status
pb = np.zeros((60, 60, 30), bool); box(pb, 20, 40, 20, 40, 0, 30, True)
pc = np.zeros_like(pb); box(pc, 42, 43, 20, 40, 0, 30, True)
r1 = M.required_neighbour_distance(pc, pb, np.ones(30, bool))
r2 = M.required_neighbour_distance(np.zeros_like(pb), pb, np.ones(30, bool))
r3 = M.required_neighbour_distance(pc, np.zeros_like(pb), np.ones(30, bool))
case('required neighbour distance', within(r1['median_mm'], 1.9, 2.1) and r2['status'] == 'class-not-predicted' and r3['status'] == 'neighbour-not-predicted', (r1, r2['status'], r3['status']))

# 16 a false-positive bone blob inside labelled muscle, 25 px from the labelled bone: not a bone boundary (the reference has
#    no bone here or across), so the bone surface metric ignores it and bone Dice sees it; the hole it makes in the predicted
#    muscle IS a muscle boundary error and is measured against the nearest true muscle boundary
ref = block(); box(ref, 0, 60, 0, 60, 0, 30, MUSCLE); box(ref, 5, 15, 5, 15, 5, 25, BONE)
pred = ref.copy(); box(pred, 40, 50, 40, 50, 5, 25, BONE)
mb, vb, db, dvb = score(ref, pred, BONE)
mm, vm, dm, dvm = score(ref, pred, MUSCLE)
case('false-positive blob: bone Dice sees it, muscle surface measures the hole', mb['p95_mm'] == 0.0 and db < 1.0 and mm['p95_mm'] is not None and mm['p95_mm'] > 10.0, (mb['p95_mm'], db, mm['p95_mm']))

failed = [c['case'] for c in results if not c['ok']]
print(json.dumps({'cases': len(results), 'all_as_expected': not failed, 'failed': failed, 'detail': [c for c in results if not c['ok']]}, default=str))
sys.exit(1 if failed else 0)
