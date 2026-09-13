"""The one frozen implementation of the pilot metrics (registry/machine-acceptance-protocol-v1.json, revised after the
Codex audit of afec927): Dice with an eligibility mask, and the symmetric pooled voxel-surface p95 with original k
coordinates, per k-run, with surface caps next to ineligible voxels removed.

Definitions (every consumer imports these; the protocol names this file):
  eligible   boolean volume: True where a voxel counts (a scoring slice, not ignore). Everything else is outside every
             metric, numerator and denominator.
  dice       2 |P & R & E| / (|P & E| + |R & E|); None when both are empty on E.
  surface    voxels of a mask (restricted to E) that have a 6-neighbour outside the mask, computed inside each k-run
             separately (a run = consecutive k positions of one band; runs are never concatenated, so the gap between
             bands and any missing slice never creates neighbours).
  caps       a surface voxel whose 6-neighbourhood touches an ineligible voxel or any face of the run's volume (the two k
             faces of the run and the four i/j faces of the grid) is a cap created by the crop or the ignore region, not by
             the object. Caps are removed from BOTH the source and the target set of every direction (symmetric,
             conservative: a distance is never manufactured against an artificial face). The number of surface voxels
             kept and removed per mask is reported as `support`. If a mask keeps no observable surface voxel while the
             other mask has one, the run is 'no-observable-surface' and its p95 is undefined.
  distance   nearest target-surface voxel, Euclidean in mm with spacing (0.666, 0.666, 0.333), by EDT on the target
             surface complement inside the run.
  p95        95th percentile of the pooled distances, both directions, all runs. Emptiness is decided per run BEFORE any
             surface or cap extraction: prediction empty where the reference exists (overall or in one run) -> p95 None,
             status 'empty-prediction' / 'empty-prediction-in-run' (fails every surface criterion). Empty reference
             everywhere: None, 'no-reference'. The guarantee is per RUN: a small omitted component inside a run that also
             holds a correctly predicted component is NOT detected as emptiness; p95 can miss small components (limit).
             A run with prediction but no reference ('false-positives-only', e.g. cartilage in band 2): no distance is
             defined there; the run is left out of the surface pool and its voxels are reported; they still count in the
             pooled Dice.
  tolerance  a perturbation counts as degrading Dice when it drops by at least DICE_TOL and as degrading p95 when it rises
             by at least P95_TOL (one slice spacing); p95 values are quantised by the grid and ties happen.

Nothing here is anatomy: it compares two label volumes on a grid.
"""
import numpy as np
from scipy import ndimage

SPACING = (0.666, 0.666, 0.333)          # (i, j, k) mm
DICE_TOL = 0.01
P95_TOL = 0.333
STRUCT6 = ndimage.generate_binary_structure(3, 1)


def dice(pred, ref, eligible):
    p = pred & eligible
    r = ref & eligible
    den = int(p.sum()) + int(r.sum())
    if den == 0:
        return None
    return float(2 * int((p & r).sum()) / den)


def _surface(mask):
    """6-connected surface voxels of a boolean (i, j, k) volume; the volume boundary counts as outside."""
    if not mask.any():
        return mask
    inner = ndimage.binary_erosion(mask, STRUCT6, border_value=0)
    return mask & ~inner


def _caps(eligible):
    """Voxels whose 6-neighbourhood touches an ineligible voxel or any of the six faces of the run volume (two k faces of the
    run, four i/j faces of the grid)."""
    inel = ~eligible
    grown = ndimage.binary_dilation(inel, STRUCT6, border_value=1)
    return grown


def _distances(src_surf, tgt_surf, spacing):
    if not src_surf.any():
        return np.zeros(0)
    if not tgt_surf.any():
        return np.full(int(src_surf.sum()), np.inf)
    edt = ndimage.distance_transform_edt(~tgt_surf, sampling=spacing)
    return edt[src_surf]


def k_runs(ks):
    """Consecutive runs of sorted k positions -> list of (k_first, k_last)."""
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
    """pred, ref, eligible: boolean (i, j, K) volumes of the block (k index = k - k_first). runs: [(k_lo, k_hi)] in Denver k.

    Returns dict(p95_mm, mean_mm, n_distances, status, support, per_run=[...])."""
    pooled, per_run = [], []
    any_ref, any_pred = False, False
    kept_p = kept_r = caps_p = caps_r = 0
    for lo, hi in runs:
        sl = slice(lo - k_first, hi - k_first + 1)
        E = eligible[:, :, sl]
        P = pred[:, :, sl] & E
        R = ref[:, :, sl] & E
        r_any, p_any = bool(R.any()), bool(P.any())
        any_ref |= r_any; any_pred |= p_any
        if not r_any and not p_any:
            per_run.append({'k': [lo, hi], 'n_distances': 0, 'status': 'empty-both'}); continue
        if not r_any:
            # false positives in a run without reference: no surface distance is defined there; the voxels count in the
            # pooled Dice (they are in |P & E|) and are reported here, the run is left out of the surface pool
            per_run.append({'k': [lo, hi], 'n_distances': 0, 'status': 'false-positives-only', 'n_prediction_voxels': int(P.sum())}); continue
        if not p_any:
            # decided before any surface extraction: the reference exists here and the prediction has nothing
            per_run.append({'k': [lo, hi], 'n_distances': 0, 'status': 'empty-prediction-in-run', 'n_reference_voxels': int(R.sum())})
            pooled.append(np.array([np.inf])); continue
        caps = _caps(E)
        sP, sR = _surface(P) & ~caps, _surface(R) & ~caps
        cp, cr = int((_surface(P) & caps).sum()), int((_surface(R) & caps).sum())
        kept_p += int(sP.sum()); kept_r += int(sR.sum()); caps_p += cp; caps_r += cr
        sup = {'prediction_surface_kept': int(sP.sum()), 'prediction_surface_caps_removed': cp, 'reference_surface_kept': int(sR.sum()), 'reference_surface_caps_removed': cr}
        if not sP.any() or not sR.any():
            per_run.append({'k': [lo, hi], 'n_distances': 0, 'status': 'no-observable-surface', 'support': sup})
            pooled.append(np.array([np.inf])); continue
        d1 = _distances(sP, sR, spacing)     # prediction -> reference
        d2 = _distances(sR, sP, spacing)     # reference -> prediction
        d = np.concatenate([d1, d2])
        pooled.append(d)
        per_run.append({'k': [lo, hi], 'n_distances': int(d.size), 'p95_mm': float(np.quantile(d, 0.95)), 'status': 'ok', 'support': sup})
    support = {'prediction_surface_kept': kept_p, 'prediction_surface_caps_removed': caps_p, 'reference_surface_kept': kept_r, 'reference_surface_caps_removed': caps_r}
    if not any_ref:
        return {'p95_mm': None, 'mean_mm': None, 'n_distances': 0, 'status': 'no-reference', 'support': support, 'per_run': per_run}
    if not any_pred:
        return {'p95_mm': None, 'mean_mm': None, 'n_distances': 0, 'status': 'empty-prediction', 'support': support, 'per_run': per_run}
    d = np.concatenate(pooled) if pooled else np.zeros(0)
    if d.size == 0:
        return {'p95_mm': None, 'mean_mm': None, 'n_distances': 0, 'status': 'no-surface', 'support': support, 'per_run': per_run}
    if not np.isfinite(d).all():
        bad = [r['status'] for r in per_run if r['status'] in ('empty-prediction-in-run', 'no-observable-surface')]
        st = 'empty-prediction-in-run' if 'empty-prediction-in-run' in bad else 'no-observable-surface'
        return {'p95_mm': None, 'mean_mm': None, 'n_distances': int(np.isfinite(d).sum()), 'status': st, 'support': support, 'per_run': per_run}
    return {'p95_mm': float(np.quantile(d, 0.95)), 'mean_mm': float(d.mean()), 'n_distances': int(d.size), 'status': 'ok', 'support': support, 'per_run': per_run}


def degrades(base, perturbed, dice_tol=DICE_TOL, p95_tol=P95_TOL):
    """Does the perturbed result score worse than the base by at least the tolerances? Returns dict of booleans (None = not decidable)."""
    out = {}
    if base.get('dice') is None or perturbed.get('dice') is None:
        out['dice'] = None
    else:
        out['dice'] = bool(perturbed['dice'] <= base['dice'] - dice_tol)
    bp, pp = base.get('p95_mm'), perturbed.get('p95_mm')
    if bp is None:
        out['p95'] = None
    elif pp is None:
        out['p95'] = True            # undefined (empty or one-sided) is worse than a finite figure
    else:
        out['p95'] = bool(pp >= bp + p95_tol)
    return out


# ---- perturbations used by the controls (all in-plane, per k slice, on boolean (i, j, K) volumes) ----

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
    """2D cross (4-neighbour) dilation applied slice by slice; the k axis is untouched."""
    st = np.zeros((3, 3, 1), bool); st[1, :, 0] = True; st[:, 1, 0] = True
    return ndimage.binary_dilation(mask, st, iterations=iterations)


def erode_inplane(mask, iterations):
    st = np.zeros((3, 3, 1), bool); st[1, :, 0] = True; st[:, 1, 0] = True
    return ndimage.binary_erosion(mask, st, iterations=iterations, border_value=0)
