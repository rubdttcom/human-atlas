"""The one frozen implementation of the pilot metrics under acceptance protocol version 2
(registry/machine-acceptance-protocol-v2.json). scripts/cryo_metrics.py stays the frozen version 1 and is
not imported here: the two implementations are separate on purpose, so that a version 1 report can always
be re-run against the file that produced it.

Written on 2026-09-20, AFTER both pilot variants had been scored under version 1, from the post hoc
analysis in docs/findings-2026-09-20-observable-surface-posthoc.md. It therefore grades only variants
trained after that date; the evaluator refuses earlier ones.

Definitions (boolean (i, j, K) volumes, k index = k - k_first; one k-run per band, runs never concatenated):
  eligible   E: scoring slice and reference class != ignore. Unchanged from version 1. Outside E nothing
             enters a numerator or a denominator of Dice.
  dice       2 |P & R & E| / (|P & E| + |R & E|); None when both are empty on E. Unchanged from version 1.
  face       a voxel on one of the six faces of the run volume (two k faces, four i/j faces of the grid).
             Removed from every surface, source or target: a crop is not a boundary.
  surface    6-connected boundary voxels of a mask inside the run, computed on the UNRESTRICTED mask
             (prediction as predicted, reference as labelled), so that the ignore region creates no
             pseudo-boundary. Callers pass unrestricted masks.
  observable a surface voxel of mask X is observable when it is eligible AND at least one of its 6-neighbours
             outside X is eligible: the reference labels both sides of that boundary.
  attributed an observable PREDICTION surface voxel of class c counts as a source only where the reference
             assigns c to that voxel or to an eligible voxel across the boundary. A boundary of class c that the
             reference places entirely inside another class (a rim of predicted muscle inside labelled bone) is
             a boundary error of THAT class and is measured there, once, not against a reference of c that may
             be incomplete (Denver labels every bone of the region but not every muscle). Reference sources are
             observable reference surface voxels; they are of class c by construction.
  target     the FULL surface of the other mask minus faces. A reference structure is labelled completely,
             so every voxel of its boundary is an observed boundary of that class even where the class of the
             voxel outside is unknown; the prediction surface is defined everywhere the model predicted.
             A larger target can only shorten a distance, never manufacture one.
  distances  attributed prediction surface -> full reference surface, observable reference surface -> full
             prediction surface, Euclidean in mm with spacing (0.666, 0.666, 0.333) by EDT on the target
             complement inside the run.
  p95        95th percentile of the pooled distances, both directions, all runs. Emptiness statuses are decided
             per run before any surface extraction exactly as in version 1: reference and no prediction ->
             'empty-prediction-in-run' (undefined, fails); prediction and no reference -> 'false-positives-only'
             (left out of the pool, voxels reported; they still count in the pooled Dice); no reference anywhere
             -> 'no-reference'. A run with reference support whose attributed prediction source set or observable
             reference source set is empty is 'no-observable-surface' (undefined, fails).
  volume on ignore  per class and band, the number of predicted voxels of the class on scoring slices whose
             reference is ignore. Reported, never scored: an unlabelled voxel may hold a structure Denver omitted.
  required neighbour  per class with a required neighbour class (cartilage -> bone), the in-plane distance from
             every predicted voxel of the class on scoring slices to the nearest PREDICTED voxel of the neighbour
             class IN THE SAME SECTION (2D EDT per slice, spacing 0.666 x 0.666, whole slice, blind to the ignore
             mask); median, p90, max, and the number of voxels whose section holds no predicted neighbour (their
             distance is infinite; an infinite median is undefined and fails). Bone in a neighbouring section
             never counts (external audit of b02dd3b, finding 2: the first implementation ran a 3D EDT over the
             whole volume, so bone 0.333 mm away in the next section, or outside the scoring slices, satisfied
             the term). A class that exists only on the surface of another cannot be predicted far from it.
             Compared with the same figure measured on the reference (reference cartilage -> reference bone,
             1.332 mm on band 1, the same under the 3D definition) plus one in-plane diagonal pixel.
  tolerance  a perturbation degrades Dice when it drops by at least 0.01 and p95 when it rises by at least
             0.333 mm (one slice spacing); ties within tolerance count as not degraded. Unchanged.

What the surface metric still cannot see: a prediction boundary against ignore contributes no distance; it is
counted in support as prediction_surface_against_ignore. Nothing here is anatomy: it compares two label volumes
on a grid.
"""
import numpy as np
from scipy import ndimage

SPACING = (0.666, 0.666, 0.333)          # (i, j, k) mm
DICE_TOL = 0.01
P95_TOL = 0.333
DIAGONAL_PX_MM = 0.9418662325404814      # one in-plane diagonal pixel, 0.666 * sqrt(2)
STRUCT6 = ndimage.generate_binary_structure(3, 1)


def dice(pred, ref, eligible):
    p = pred & eligible
    r = ref & eligible
    den = int(p.sum()) + int(r.sum())
    if den == 0:
        return None
    return float(2 * int((p & r).sum()) / den)


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
    outside_elig = (~mask) & E
    touch = ndimage.binary_dilation(outside_elig, STRUCT6, border_value=0)
    return surf & E & touch


def _attributed(pred, obs_pred_surf, ref):
    """Observable prediction surface voxels where the reference is the class here or across the boundary."""
    across = ndimage.binary_dilation(ref & ~pred, STRUCT6, border_value=0)
    return obs_pred_surf & (ref | across)


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


def k_runs(ks):
    ks = sorted(ks)
    if not ks:
        return []
    runs, start, prev = [], ks[0], ks[0]
    for k in ks[1:]:
        if k != prev + 1:
            runs.append((start, prev)); start = k
        prev = k
    runs.append((start, prev))
    return runs


def surface_p95(pred, ref, eligible, runs, k_first, spacing=SPACING):
    """pred, ref: boolean volumes of ONE class, unrestricted by eligibility. Returns dict(p95_mm, p50_mm, mean_mm,
    n_distances, status, support, per_run, prediction_to_reference, reference_to_prediction)."""
    pooled, per_run, a_all, b_all = [], [], [], []
    any_ref = any_pred = False
    tot = {'prediction_surface': 0, 'prediction_surface_observable': 0, 'prediction_surface_attributed': 0, 'prediction_surface_against_ignore': 0,
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
        aP = _attributed(P, oP, R)
        sup = {'prediction_surface': int(sP.sum()), 'prediction_surface_observable': int(oP.sum()), 'prediction_surface_attributed': int(aP.sum()),
               'prediction_surface_against_ignore': int((sP & E & ~oP).sum()),
               'reference_surface': int(sR.sum()), 'reference_surface_observable': int(oR.sum()), 'reference_surface_against_ignore': int((sR & ~oR).sum())}
        for k in tot:
            tot[k] += sup[k]
        if not aP.any() or not oR.any():
            per_run.append({'k': [lo, hi], 'n_distances': 0, 'status': 'no-observable-surface', 'support': sup})
            pooled.append(np.array([np.inf])); continue
        dA = _distances(aP, sR, spacing)
        dB = _distances(oR, sP, spacing)
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


def volume_on_ignore(pred, ref_is_ignore, slice_eligible):
    """Predicted voxels of a class on scoring slices whose reference is ignore. Reported, never scored."""
    return int((pred & ref_is_ignore & slice_eligible[None, None, :]).sum())


def required_neighbour_distance(pred_class, pred_neighbour, slice_eligible, spacing=SPACING):
    """In-plane distance from every predicted voxel of a class (scoring slices, whole slice, blind to ignore) to the
    nearest predicted voxel of its required neighbour class IN THE SAME SECTION. 2D EDT per slice: a neighbour voxel in
    another section never counts, whatever the slice spacing. None figures when the class is not predicted; a section
    without any predicted neighbour gives its class voxels an infinite distance (counted in
    voxels_without_neighbour_in_section); an infinite median is undefined (median_mm None) and fails the criterion."""
    src = pred_class & slice_eligible[None, None, :]
    n = int(src.sum())
    if n == 0:
        return {'n': 0, 'median_mm': None, 'p90_mm': None, 'max_mm': None, 'voxels_without_neighbour_in_section': 0, 'status': 'class-not-predicted'}
    if not (pred_neighbour & slice_eligible[None, None, :]).any():
        return {'n': n, 'median_mm': None, 'p90_mm': None, 'max_mm': None, 'voxels_without_neighbour_in_section': n, 'status': 'neighbour-not-predicted'}
    parts = []
    for kk in np.flatnonzero(slice_eligible):
        c = src[:, :, kk]
        if not c.any():
            continue
        b = pred_neighbour[:, :, kk]
        if not b.any():
            parts.append(np.full(int(c.sum()), np.inf)); continue
        parts.append(ndimage.distance_transform_edt(~b, sampling=spacing[:2])[c])
    d = np.concatenate(parts)
    without = int((~np.isfinite(d)).sum())
    med = float(np.median(d))
    fin = d[np.isfinite(d)]
    if not np.isfinite(med):
        return {'n': n, 'median_mm': None, 'p90_mm': None, 'max_mm': float(fin.max()) if fin.size else None,
                'voxels_without_neighbour_in_section': without, 'status': 'neighbour-absent-in-most-sections'}
    p90 = float(np.quantile(d, 0.9))
    return {'n': n, 'median_mm': med, 'p90_mm': p90 if np.isfinite(p90) else None, 'max_mm': float(fin.max()),
            'voxels_without_neighbour_in_section': without, 'status': 'ok'}


def degrades(base, perturbed, dice_tol=DICE_TOL, p95_tol=P95_TOL):
    out = {}
    if base.get('dice') is None or perturbed.get('dice') is None:
        out['dice'] = None
    else:
        out['dice'] = bool(perturbed['dice'] <= base['dice'] - dice_tol)
    bp, pp = base.get('p95_mm'), perturbed.get('p95_mm')
    if bp is None:
        out['p95'] = None
    elif pp is None:
        out['p95'] = True
    else:
        out['p95'] = bool(pp >= bp + p95_tol)
    return out


def mirror_i(mask):
    return mask[::-1, :, :]


def shift_i(mask, px):
    out = np.zeros_like(mask)
    if px > 0:
        out[px:, :, :] = mask[:-px, :, :]
    elif px < 0:
        out[:px, :, :] = mask[-px:, :, :]
    else:
        out[:] = mask
    return out


def dilate_inplane(mask, iterations):
    st = np.zeros((3, 3, 1), bool); st[1, :, 0] = True; st[:, 1, 0] = True
    return ndimage.binary_dilation(mask, st, iterations=iterations)


def erode_inplane(mask, iterations):
    st = np.zeros((3, 3, 1), bool); st[1, :, 0] = True; st[:, 1, 0] = True
    return ndimage.binary_erosion(mask, st, iterations=iterations, border_value=0)
