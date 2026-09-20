"""Synthetic checks of scripts/cryo_posthoc_surface.py against scripts/cryo_metrics.py (v1).

Each case builds a small block with a labelled structure, an ignore region and a prediction, and states
what both metrics must report. The point of the file is case 3: the v1 artefact reproduced on a toy, and
the post hoc metric reporting the boundary error instead. Prints one JSON line; exit 1 on any failure.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cryo_metrics as V1  # noqa: E402
import cryo_posthoc_surface as PH  # noqa: E402

SP = PH.SPACING
K0 = 1000
IGN = 255


def block(shape=(60, 60, 30)):
    ref = np.full(shape, IGN, np.uint8)          # everything unlabelled
    return ref


def box(vol, i0, i1, j0, j1, k0, k1, val):
    vol[i0:i1, j0:j1, k0:k1] = val


def run_case(name, ref, pred_cls, ref_cls, expect):
    runs = [(K0, K0 + ref.shape[2] - 1)]
    E = ref != IGN
    v1 = V1.surface_p95(pred_cls & E, ref_cls & E, E, runs, K0)
    ph = PH.observable_surface_p95(pred_cls, ref_cls, E, runs, K0)
    ok = True
    notes = []
    for key, (lo, hi) in expect.get('v1', {}).items():
        v = v1.get(key)
        if v is None or not (lo <= v <= hi):
            ok = False; notes.append(f'v1 {key}={v} not in [{lo},{hi}]')
    for key, (lo, hi) in expect.get('ph', {}).items():
        v = ph.get(key)
        if v is None or not (lo <= v <= hi):
            ok = False; notes.append(f'ph {key}={v} not in [{lo},{hi}]')
    for key, st in expect.get('status', {}).items():
        got = (v1 if key == 'v1' else ph)['status']
        if got != st:
            ok = False; notes.append(f'{key} status {got} != {st}')
    return {'case': name, 'ok': ok, 'v1_p95': v1.get('p95_mm'), 'ph_p95': ph.get('p95_mm'), 'ph_status': ph['status'], 'notes': notes}


def main():
    out = []
    # case 1: fully labelled block (bone inside muscle), prediction == reference -> 0 under both
    ref = block(); box(ref, 0, 60, 0, 60, 0, 30, 3); box(ref, 20, 40, 20, 40, 5, 25, 1)
    R = ref == 1
    out.append(run_case('identity, fully labelled', ref, R.copy(), R, {'v1': {'p95_mm': (0, 0)}, 'ph': {'p95_mm': (0, 0)}}))
    # case 2: fully labelled, prediction eroded by 1 px in-plane -> both report 0.666
    P = ndimage.binary_erosion(R, np.array([[[0], [1], [0]], [[1], [1], [1]], [[0], [1], [0]]], bool))
    out.append(run_case('1 px under-segmentation, fully labelled', ref, P, R, {'v1': {'p95_mm': (0.6, 0.7)}, 'ph': {'p95_mm': (0.6, 0.7)}}))
    # case 3: the v1 artefact. Bone surrounded by ignore, with a small labelled muscle patch touching it; prediction misses a
    # 3 px rim (predicts it as muscle). v1: the bone/ignore reference surface is a cap and goes, the inner prediction
    # surface stays, distances run to the remnant near the patch -> p95 far above 2 mm. Post hoc: p95 about 2 mm.
    ref = block(); box(ref, 20, 40, 20, 40, 5, 25, 1); box(ref, 40, 45, 25, 30, 10, 12, 3)
    R = ref == 1
    P = ndimage.binary_erosion(R, np.array([[[0], [1], [0]], [[1], [1], [1]], [[0], [1], [0]]], bool), iterations=3)
    out.append(run_case('3 px rim missed, structure surrounded by ignore', ref, P, R,
                        {'v1': {'p95_mm': (5.0, 100.0)}, 'ph': {'p95_mm': (1.9, 2.1)}}))
    # case 4: prediction extends bone 5 px into ignore, boundary inside labelled tissue exact -> post hoc 0 (unobservable
    # extension counted, not scored); v1 also 0 because P is masked by E
    ref = block(); box(ref, 20, 40, 20, 40, 5, 25, 1); box(ref, 40, 45, 25, 30, 10, 12, 3)
    R = ref == 1
    P = R.copy(); box(P, 20, 40, 15, 20, 5, 25, True)
    r = run_case('5 px extension into ignore', ref, P, R, {'ph': {'p95_mm': (0, 0)}})
    ph = PH.observable_surface_p95(P, R, ref != IGN, [(K0, K0 + 29)], K0)
    if ph['support']['prediction_surface_against_ignore'] <= 0:
        r['ok'] = False; r['notes'].append('extension into ignore not counted')
    out.append(r)
    # case 5: shift by 3 px in i in a fully labelled block degrades post hoc p95 to about 2 mm
    ref = block(); box(ref, 0, 60, 0, 60, 0, 30, 3); box(ref, 20, 40, 20, 40, 5, 25, 1)
    R = ref == 1
    out.append(run_case('3 px shift, fully labelled', ref, V1.shift_i(R, 3), R, {'ph': {'p95_mm': (1.9, 2.1)}, 'v1': {'p95_mm': (1.9, 2.1)}}))
    # case 6: structure touching the k faces of the run is not penalised by the crop
    ref = block(); box(ref, 0, 60, 0, 60, 0, 30, 3); box(ref, 20, 40, 20, 40, 0, 30, 1)
    R = ref == 1
    out.append(run_case('identity through both k faces', ref, R.copy(), R, {'ph': {'p95_mm': (0, 0)}}))
    # case 7: prediction empty where the reference exists
    out.append(run_case('empty prediction', ref, np.zeros_like(R), R, {'status': {'ph': 'empty-prediction', 'v1': 'empty-prediction'}}))
    # case 8: false positives in a run without reference
    ref = block(); box(ref, 0, 60, 0, 60, 0, 30, 3)
    R = ref == 1
    P = np.zeros_like(R); box(P, 20, 30, 20, 30, 5, 10, True)
    out.append(run_case('false positives only', ref, P, R, {'status': {'ph': 'no-reference', 'v1': 'no-reference'}}))
    failed = [c['case'] for c in out if not c['ok']]
    print(json.dumps({'cases': len(out), 'all_as_expected': not failed, 'failed': failed, 'detail': out}))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
