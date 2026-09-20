"""Post hoc surface metric of the cryosection pilot: distances between OBSERVABLE boundaries.

This is NOT protocol v1. scripts/cryo_metrics.py stays the one frozen implementation and its results
stand on the record. This module was written on 2026-09-20, after both variants had been scored, to
test the claim of docs/findings-2026-09-14-rgb-only-first-score.md section 1: that the v1 surface p95
measures the caps rule and not a boundary error. Every number it produces is labelled post hoc and
replaces nothing (docs/findings-2026-09-20-observable-surface-posthoc.md).

Why v1 is asymmetric on this data. v1 removes from BOTH surfaces every voxel whose 6-neighbourhood
touches an ineligible (ignore) voxel. Denver's structures are surrounded by unlabelled tissue, so
79 % of the reference bone surface goes, while a prediction boundary that lies INSIDE the reference
structure (an under-segmented rim) touches no ignore and is kept. Those kept prediction voxels are
then measured against a 21 % remnant of the reference surface, tens of millimetres away.

Definitions here (boolean (i, j, K) volumes, k index = k - k_first, per k-run as in v1):
  E          eligible: scoring slice and reference != ignore. Unchanged from v1.
  face       a voxel on one of the six faces of the run volume (two k faces, four i/j faces of the
             grid). Removed from every surface, source or target: it is a crop, not a boundary.
  surface    6-connected boundary voxels of a mask inside the run, computed on the UNRESTRICTED mask
             (prediction as predicted, reference as labelled), so that the ignore region never
             creates a pseudo-boundary.
  observable a surface voxel of mask X is observable when it is eligible AND at least one of its
             6-neighbours outside X is eligible: the reference labels both sides of that boundary,
             so it can say whether the boundary belongs there. A boundary against ignore is not
             observable and is not a source of any distance.
  target     the FULL surface of the other mask minus faces. A reference structure is labelled
             completely, so every voxel of its boundary is an observed boundary of that class, even
             where the class of the outside voxel is unknown; the full prediction surface is defined
             everywhere the model predicted. A larger target can only shorten a distance, never
             manufacture one.
  distances  observable prediction surface -> full reference surface, and observable reference
             surface -> full prediction surface, Euclidean in mm with spacing (0.666, 0.666, 0.333).
  p95        95th percentile of the pooled distances, both directions, all runs. Emptiness statuses
             ('empty-prediction', 'empty-prediction-in-run', 'false-positives-only', 'no-reference')
             are decided per run before any surface extraction exactly as in v1. A run whose
             observable source set is empty on one side while the other has support is
             'no-observable-surface' and its p95 is undefined.

What this metric still cannot see: a prediction boundary against ignore (over- or under-extension of
a class into unlabelled tissue) contributes no source distance. It is reported as a count. Nothing
here is anatomy: it compares two label volumes on a grid.
"""
import numpy as np
from scipy import ndimage

SPACING = (0.666, 0.666, 0.333)
STRUCT6 = ndimage.generate_binary_structure(3, 1)


def _surface(mask):
    if not mask.any():
        return mask
    inner = ndimage.binary_erosion(mask, STRUCT6, border_value=0)
    return mask & ~inner


def _faces(shape):
    f = np.zeros(shape, bool)
    f[0, :, :] = f[-1, :, :] = True
    f[:, 0, :] = f[:, -1, :] = True
    f[:, :, 0] = f[:, :, -1] = True
    return f


def _observable(mask, surf, E):
    """Surface voxels of mask that are eligible and have an eligible 6-neighbour outside the mask."""
    outside_elig = (~mask) & E
    touch = ndimage.binary_dilation(outside_elig, STRUCT6, border_value=0)
    return surf & E & touch


def _distances(src, tgt, spacing):
    if not src.any():
        return np.zeros(0)
    if not tgt.any():
        return np.full(int(src.sum()), np.inf)
    edt = ndimage.distance_transform_edt(~tgt, sampling=spacing)
    return edt[src]


def _stats(d):
    d = d[np.isfinite(d)]
    if d.size == 0:
        return {'n': 0}
    return {'n': int(d.size), 'p50_mm': float(np.quantile(d, 0.5)), 'p95_mm': float(np.quantile(d, 0.95)), 'mean_mm': float(d.mean()), 'max_mm': float(d.max())}


def observable_surface_p95(pred, ref, eligible, runs, k_first, spacing=SPACING):
    """pred, ref: boolean volumes of one class, UNRESTRICTED by eligibility. eligible: E. runs: [(k_lo, k_hi)] in Denver k."""
    pooled, per_run = [], []
    a_all, b_all = [], []
    any_ref = any_pred = False
    tot = {'prediction_surface': 0, 'prediction_surface_observable': 0, 'prediction_surface_against_ignore': 0,
           'reference_surface': 0, 'reference_surface_observable': 0, 'reference_surface_against_ignore': 0}
    for lo, hi in runs:
        sl = slice(lo - k_first, hi - k_first + 1)
        E = eligible[:, :, sl]
        P, R = pred[:, :, sl], ref[:, :, sl]
        r_any, p_any = bool((R & E).any()), bool((P & E).any())
        any_ref |= r_any; any_pred |= p_any
        if not r_any and not p_any:
            per_run.append({'k': [lo, hi], 'n_distances': 0, 'status': 'empty-both'}); continue
        if not r_any:
            per_run.append({'k': [lo, hi], 'n_distances': 0, 'status': 'false-positives-only', 'n_prediction_voxels': int((P & E).sum())}); continue
        if not p_any:
            per_run.append({'k': [lo, hi], 'n_distances': 0, 'status': 'empty-prediction-in-run', 'n_reference_voxels': int((R & E).sum())})
            pooled.append(np.array([np.inf])); continue
        faces = _faces(E.shape)
        sP, sR = _surface(P) & ~faces, _surface(R) & ~faces
        oP, oR = _observable(P, sP, E), _observable(R, sR, E)
        sup = {'prediction_surface': int(sP.sum()), 'prediction_surface_observable': int(oP.sum()),
               'prediction_surface_against_ignore': int((sP & E & ~oP).sum()),
               'reference_surface': int(sR.sum()), 'reference_surface_observable': int(oR.sum()),
               'reference_surface_against_ignore': int((sR & ~oR).sum())}
        for k in tot:
            tot[k] += sup[k]
        if not oP.any() or not oR.any():
            per_run.append({'k': [lo, hi], 'n_distances': 0, 'status': 'no-observable-surface', 'support': sup})
            pooled.append(np.array([np.inf])); continue
        dA = _distances(oP, sR, spacing)     # observable prediction boundary -> full reference boundary
        dB = _distances(oR, sP, spacing)     # observable reference boundary -> full prediction boundary
        d = np.concatenate([dA, dB])
        pooled.append(d); a_all.append(dA); b_all.append(dB)
        per_run.append({'k': [lo, hi], 'n_distances': int(d.size), 'p95_mm': float(np.quantile(d, 0.95)), 'status': 'ok', 'support': sup,
                        'prediction_to_reference': _stats(dA), 'reference_to_prediction': _stats(dB)})
    base = {'support': tot, 'per_run': per_run}
    if not any_ref:
        return {'p95_mm': None, 'mean_mm': None, 'n_distances': 0, 'status': 'no-reference', **base}
    if not any_pred:
        return {'p95_mm': None, 'mean_mm': None, 'n_distances': 0, 'status': 'empty-prediction', **base}
    d = np.concatenate(pooled) if pooled else np.zeros(0)
    if d.size == 0:
        return {'p95_mm': None, 'mean_mm': None, 'n_distances': 0, 'status': 'no-surface', **base}
    if not np.isfinite(d).all():
        bad = [r['status'] for r in per_run if r['status'] in ('empty-prediction-in-run', 'no-observable-surface')]
        st = 'empty-prediction-in-run' if 'empty-prediction-in-run' in bad else 'no-observable-surface'
        return {'p95_mm': None, 'mean_mm': None, 'n_distances': int(np.isfinite(d).sum()), 'status': st, **base}
    return {'p95_mm': float(np.quantile(d, 0.95)), 'p50_mm': float(np.quantile(d, 0.5)), 'mean_mm': float(d.mean()), 'n_distances': int(d.size), 'status': 'ok',
            'prediction_to_reference': _stats(np.concatenate(a_all)), 'reference_to_prediction': _stats(np.concatenate(b_all)), **base}
