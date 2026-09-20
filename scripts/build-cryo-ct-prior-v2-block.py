"""Build version 2 of the CT prior channels of one cryosection block (rgb-plus-ct-prior under protocol version 2).

Input for the rgb-plus-ct-prior variant only. The prior never enters the loss target, the reference or the metrics: the
target stays registry/cryo-tissue-map.json applied to the Denver original labels (tissue-classes.nii.gz). The design
and every source are in registry/cryo-ct-prior-map-v2.json; version 1 (one model, three binary channels) stays in
registry/cryo-ct-prior-map.json and scripts/build-cryo-ct-prior-block.py, unchanged, for the two version 1 runs.

  CT grid:   bone vote of the eligible models (TotalSegmentator total bone labels, MOOSE four bone tasks, Skellytour
             inside its crop), strict majority; disagreement = some but not all eligible models say bone;
             muscle = TotalSegmentator muscle labels; bone wins a conflict.
  block:     nearest-neighbour sample of the class and disagreement volumes at the block voxel centres through
             inverse(nlm-ct-to-vhf) (the version 1 sampler, unchanged), then the in-plane distance to consensus bone
             per section, clipped at 15 mm.

  .venv/bin/python scripts/build-cryo-ct-prior-v2-block.py --block data/derived/nlm-vhf/cryosections/block2 [--selftest]

Writes <block>/ct-prior-v2-{bone,bone-disagreement,bone-distance,muscle}.nii.gz (uint8, (i, j, k), the block affine)
and generated/cryo-ct-prior-v2-block2.json with the vote figures on the CT grid and the coverage of the Denver reference
per class and stratum, side by side with the version 1 prior. Nothing here is anatomy.
"""
import argparse
import importlib.util
import json
import time
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
MAP_V2 = ROOT / 'registry/cryo-ct-prior-map-v2.json'
MAP_V1 = ROOT / 'registry/cryo-ct-prior-map.json'
TRANSFORM = ROOT / 'transforms/nlm-ct-to-vhf.json'
BANDS = ROOT / 'registry/cryo-eval-bands-v1.json'
NLM = ROOT / 'data/derived/nlm-vhf'
TS = NLM / 'totalseg.nii'
COVER = NLM / 'ct-coverage-mask.nii.gz'
SKELLY = NLM / 'skellytour/skellytour_high.nii.gz'
SKELLY_MANIFEST = NLM / 'skellytour/skellytour_high.json'
SKELLY_PLAN = NLM / 'skellytour/plan.json'
MOOSE_TASKS = ('all_bones_v1', 'peripheral_bones', 'ribs', 'vertebrae')
DIST_MAX_MM = 15.0
CHANNELS = ('bone', 'bone-disagreement', 'bone-distance', 'muscle')
CLASS_VALUE = {'none': 0, 'bone': 1, 'muscle': 3}   # the class volume reuses the version 1 values; 2 (cartilage) is never written


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


V1 = _load('prior_v1', 'scripts/build-cryo-ct-prior-block.py')
sha256_file = V1.sha256_file


def moose_path(task):
    return NLM / f'moose/segmentations/clin_CT_{task}_segmentation_CT_vhf.nii.gz'


def vote_bone(masks, eligible):
    """masks and eligible: lists of bool arrays, one per model, same order.

    Returns consensus (strict majority of the eligible models), disagreement (some but not all eligible models say
    bone), votes and eligible counts. A vote outside a model's eligibility is discarded, never counted."""
    votes = np.zeros(masks[0].shape, dtype=np.uint8)
    n_elig = np.zeros(masks[0].shape, dtype=np.uint8)
    for m, e in zip(masks, eligible):
        votes += (m & e).astype(np.uint8)
        n_elig += e.astype(np.uint8)
    consensus = votes.astype(np.uint16) * 2 > n_elig
    disagreement = (votes > 0) & (votes < n_elig)
    return consensus, disagreement, votes, n_elig


def class_volume(consensus, muscle):
    """0 none, 1 consensus bone, 3 muscle; bone wins a conflict and the conflict count is returned."""
    out = np.zeros(consensus.shape, dtype=np.uint8)
    out[muscle] = CLASS_VALUE['muscle']
    out[consensus] = CLASS_VALUE['bone']
    return out, int(np.count_nonzero(consensus & muscle))


def distance_channel(bone_slice, spacing_ij, dmax=DIST_MAX_MM):
    """In-plane distance (mm) to the nearest bone voxel of the same section, clipped at dmax, as uint8 0..255.

    0 inside bone; 255 at or beyond dmax and in a section without bone (the prior is silent there, never 'far')."""
    if not bone_slice.any():
        return np.full(bone_slice.shape, 255, dtype=np.uint8)
    d = ndimage.distance_transform_edt(~bone_slice, sampling=spacing_ij)
    return np.rint(np.clip(d, 0.0, dmax) / dmax * 255.0).astype(np.uint8)


def selftest():
    # three eligible, two say bone: consensus and disagreement
    shape = (3, 3, 1)
    a = np.zeros(shape, bool); b = np.zeros(shape, bool); c = np.zeros(shape, bool)
    e = np.ones(shape, bool)
    a[0, 0] = b[0, 0] = True          # 2 of 3
    a[1, 1] = True                    # 1 of 3
    a[2, 2] = b[2, 2] = c[2, 2] = True  # 3 of 3
    cons, dis, votes, n = vote_bone([a, b, c], [e, e, e])
    assert cons[0, 0, 0] and dis[0, 0, 0], '2 of 3 must be consensus with disagreement'
    assert not cons[1, 1, 0] and dis[1, 1, 0], '1 of 3 must not be consensus'
    assert cons[2, 2, 0] and not dis[2, 2, 0], '3 of 3 must be unanimous'
    assert not cons[0, 1, 0] and not dis[0, 1, 0], 'no vote must be nothing'
    # two eligible (third model unprocessed): both must agree; one alone is not a strict majority
    e3 = np.zeros(shape, bool)
    cons, dis, votes, n = vote_bone([a, b, c], [e, e, e3])
    assert cons[0, 0, 0] and not dis[0, 0, 0], '2 of 2 is consensus without disagreement'
    assert not cons[1, 1, 0] and dis[1, 1, 0], '1 of 2 is not a strict majority'
    assert n[0, 0, 0] == 2 and votes[2, 2, 0] == 2, 'a vote outside eligibility was counted'
    # nobody eligible: nothing, even when every model says bone
    cons, dis, votes, n = vote_bone([a, b, c], [e3, e3, e3])
    assert not cons.any() and not dis.any() and votes.max() == 0, 'ineligible votes were counted'
    # class precedence
    m = np.zeros(shape, bool); m[0, 0] = True; m[1, 0] = True
    cons = np.zeros(shape, bool); cons[0, 0] = True
    cls, conflicts = class_volume(cons, m)
    assert cls[0, 0, 0] == 1 and cls[1, 0, 0] == 3 and conflicts == 1, 'bone must win the conflict, once'
    # distance: one bone pixel, 0.666 mm spacing, 3 px away = 1.998 mm -> round(255 * 1.998 / 15) = 34
    sl = np.zeros((7, 7), bool); sl[3, 3] = True
    d = distance_channel(sl, (0.666, 0.666))
    assert d[3, 3] == 0 and d[3, 6] == 34 and d[0, 3] == 34, f'distance encoding wrong: {d[3, 3]}, {d[3, 6]}, {d[0, 3]}'
    assert d[3, 0] == 34, 'distance is not symmetric'
    big = np.zeros((60, 60), bool); big[0, 0] = True
    assert distance_channel(big, (0.666, 0.666))[59, 59] == 255, 'the clip at 15 mm failed'
    assert (distance_channel(np.zeros((4, 4), bool), (0.666, 0.666)) == 255).all(), 'a section without bone must be 255'
    print(json.dumps({'selftest': 'ok'}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--block', required=True)
    ap.add_argument('--out-dir', default=None, help='where the four channel volumes go (default: the block directory)')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    t0 = time.time()

    block = Path(a.block)
    man = json.loads((block / 'manifest.json').read_text())
    pmap2 = json.loads(MAP_V2.read_text())
    pmap1 = json.loads(MAP_V1.read_text())
    tf = json.loads(TRANSFORM.read_text())
    bands = json.loads(BANDS.read_text())
    sk_man = json.loads(SKELLY_MANIFEST.read_text())
    sk_plan = json.loads(SKELLY_PLAN.read_text())
    if not sk_man.get('complete') or sk_man.get('missing'):
        raise SystemExit(json.dumps({'ok': False, 'error': 'the Skellytour merge manifest is incomplete or has missing chunks'}))
    if pmap2['version'] != 2 or pmap2['distance_max_mm'] != DIST_MAX_MM or [c['name'] for c in pmap2['channels']] != list(CHANNELS):
        raise SystemExit(json.dumps({'ok': False, 'error': 'registry/cryo-ct-prior-map-v2.json does not describe this builder'}))

    # ---- CT grid: masks, eligibility, vote ---------------------------------------------------------------
    print('loading CT label volumes', flush=True)
    ts_im = nib.load(TS)
    shape, affine = ts_im.shape, ts_im.affine
    lut1 = V1.lut_from_map(pmap1)
    ts = np.asanyarray(ts_im.dataobj)
    ts_cls = lut1[np.clip(ts, 0, len(lut1) - 1)]
    ts_bone = ts_cls == 1
    ts_muscle = ts_cls == 3
    del ts, ts_cls

    def same_grid(im, name):
        if im.shape != shape or not np.allclose(im.affine, affine, atol=1e-3):
            raise SystemExit(json.dumps({'ok': False, 'error': f'{name} is not on the TotalSegmentator CT grid'}))

    moose_bone = np.zeros(shape, bool)
    for task in MOOSE_TASKS:
        im = nib.load(moose_path(task)); same_grid(im, task)
        moose_bone |= np.asanyarray(im.dataobj) != 0
    sk_im = nib.load(SKELLY); same_grid(sk_im, 'skellytour')
    sk_bone = np.asanyarray(sk_im.dataobj) != 0
    cov_im = nib.load(COVER); same_grid(cov_im, 'coverage mask')
    coverage = np.asanyarray(cov_im.dataobj) > 0
    i0, i1, j0, j1 = sk_plan['crop']
    sk_crop = np.zeros(shape, bool)
    sk_crop[i0:i1, j0:j1, :] = True
    if (sk_bone & ~sk_crop).any():
        # the model never saw those voxels: a label there is an inconsistency of the merge, not a vote to discard
        raise SystemExit(json.dumps({'ok': False, 'error': 'Skellytour labels outside its own crop'}))
    sk_elig = sk_crop & coverage
    # a label on a voxel with coverage 0 (the rim of the circular field of view) is discarded by the eligibility rule
    # of registry/cryo-ct-prior-map-v2.json: unknown there, never a vote. The counts are recorded, not hidden.
    discarded_outside_fov = {'totalseg_bone': int(np.count_nonzero(ts_bone & ~coverage)),
                             'totalseg_muscle': int(np.count_nonzero(ts_muscle & ~coverage)),
                             'moose_bone': int(np.count_nonzero(moose_bone & ~coverage)),
                             'skellytour_bone': int(np.count_nonzero(sk_bone & ~coverage))}

    print('voting', flush=True)
    consensus, disagreement, votes, n_elig = vote_bone([ts_bone, moose_bone, sk_bone], [coverage, coverage, sk_elig])
    hist = {}
    for ne in np.unique(n_elig):
        for v in np.unique(votes[n_elig == ne]):
            hist[f'eligible_{int(ne)}_votes_{int(v)}'] = int(np.count_nonzero((n_elig == ne) & (votes == v)))
    ct_stats = {
        'grid': list(shape), 'voxel_ml': round(float(abs(np.linalg.det(affine[:3, :3])) / 1000.0), 6),
        'bone_voxels': {'totalseg': int(ts_bone.sum()), 'moose_union': int(moose_bone.sum()), 'skellytour': int(sk_bone.sum()),
                        'consensus': int(consensus.sum()), 'disagreement': int(disagreement.sum())},
        'eligible_votes_histogram': hist,
        'labels_outside_field_of_view_discarded': discarded_outside_fov,
        'pairwise_dice_bone': {
            'totalseg_moose': round(2 * int((ts_bone & moose_bone).sum()) / max(1, int(ts_bone.sum()) + int(moose_bone.sum())), 4),
            'totalseg_skellytour_in_crop': round(2 * int((ts_bone & sk_bone).sum()) / max(1, int((ts_bone & sk_elig).sum()) + int(sk_bone.sum())), 4),
            'moose_skellytour_in_crop': round(2 * int((moose_bone & sk_bone).sum()) / max(1, int((moose_bone & sk_elig).sum()) + int(sk_bone.sum())), 4),
        },
    }
    del ts_bone, moose_bone, sk_bone, votes, n_elig
    class_ct, conflicts = class_volume(consensus, ts_muscle & coverage)
    ct_stats['bone_over_muscle_conflicts'] = conflicts
    ct_stats['muscle_voxels_totalseg'] = int(np.count_nonzero(class_ct == CLASS_VALUE['muscle']))
    dis_ct = disagreement.astype(np.uint8)
    del consensus, disagreement, ts_muscle, coverage, sk_elig

    # ---- block grid: nearest-neighbour sample, then the distance channel ----------------------------------
    print('sampling onto the block grid', flush=True)
    nk, nj, ni = man['grid']['shape_kji3'][:3]
    A_block = np.array(man['grid']['ijk_to_ras_block'], dtype=np.float64)
    M_inv = np.linalg.inv(np.array(tf['matrix_row_major'], dtype=np.float64).reshape(4, 4))
    ct_inv = np.linalg.inv(affine)
    sx, sy, sz = man['grid']['spacing_mm_ijk']
    ident = np.arange(4, dtype=np.uint8)
    lut01 = np.array([0, 1], dtype=np.uint8)
    chans = {c: np.zeros((ni, nj, nk), dtype=np.uint8) for c in CHANNELS}
    in_field = np.zeros(nk, dtype=np.int64)
    for k in range(nk):
        cls, inside = V1.sample_slice(k, A_block, M_inv, ct_inv, class_ct, ident, (ni, nj))
        dis, _ = V1.sample_slice(k, A_block, M_inv, ct_inv, dis_ct, lut01, (ni, nj))
        bone = cls == CLASS_VALUE['bone']
        chans['bone'][:, :, k] = bone
        chans['bone-disagreement'][:, :, k] = dis
        chans['bone-distance'][:, :, k] = distance_channel(bone, (sx, sy))
        chans['muscle'][:, :, k] = cls == CLASS_VALUE['muscle']
        in_field[k] = int(inside.sum())
    del class_ct, dis_ct

    ref_im = nib.load(block / 'tissue-classes.nii.gz')
    out_dir = Path(a.out_dir) if a.out_dir else block
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for c in CHANNELS:
        p = out_dir / f'ct-prior-v2-{c}.nii.gz'
        nib.save(nib.Nifti1Image(chans[c], ref_im.affine, dtype=np.uint8), p)
        outputs[c] = {'file': p.name, 'sha256': sha256_file(p), 'dtype': 'uint8', 'order': '(i, j, k)'}

    # ---- coverage of the Denver reference, per stratum, side by side with version 1 ------------------------
    print('measuring coverage', flush=True)
    tissue = np.asanyarray(ref_im.dataobj)
    v1_path = block / 'ct-prior-tissue.nii.gz'
    v1 = np.asanyarray(nib.load(v1_path).dataobj) if v1_path.exists() else None
    te = bands['training_eligibility']
    k_first = man['block']['k_first']
    primary = sorted({k for lo, hi in te['primary_k_ranges'] for k in range(lo, hi + 1)})
    scoring = sorted({k for b in bands['bands'] for k in range(b['k_first'], b['k_last'] + 1)})
    labelled_values = (0, 1, 2, 3)

    def stratum(ks):
        z = np.array([k - k_first for k in ks], dtype=np.int64)
        ref = tissue[:, :, z]
        labelled = np.isin(ref, labelled_values)
        out = {'slices': len(ks)}
        for cls_name, val in (('bone', 1), ('muscle', 3)):
            ref_c = ref == val
            pri = chans[cls_name][:, :, z] > 0
            row = {'reference_voxels': int(ref_c.sum()), 'prior_voxels': int(pri.sum()),
                   'prior_recall_of_reference': round(float((pri & ref_c).sum() / max(1, ref_c.sum())), 4),
                   'prior_on_labelled_other_tissue_fraction': round(float((pri & labelled & ~ref_c).sum() / max(1, (pri & labelled).sum())), 4),
                   'prior_on_ignore_voxels': int((pri & ~labelled).sum())}
            if v1 is not None:
                pri1 = v1[:, :, z] == val
                row['v1_prior_voxels'] = int(pri1.sum())
                row['v1_prior_recall_of_reference'] = round(float((pri1 & ref_c).sum() / max(1, ref_c.sum())), 4)
                row['v1_prior_on_labelled_other_tissue_fraction'] = round(float((pri1 & labelled & ~ref_c).sum() / max(1, (pri1 & labelled).sum())), 4)
            out[cls_name] = row
        dis = chans['bone-disagreement'][:, :, z] > 0
        ref_bone = ref == 1
        out['bone_disagreement'] = {'voxels': int(dis.sum()),
                                    'on_reference_bone': int((dis & ref_bone).sum()),
                                    'on_labelled_non_bone': int((dis & labelled & ~ref_bone).sum()),
                                    'on_ignore': int((dis & ~labelled).sum())}
        dist_mm = chans['bone-distance'][:, :, z].astype(np.float64) / 255.0 * DIST_MAX_MM
        missed = ref_bone & ~(chans['bone'][:, :, z] > 0)
        out['bone_distance'] = {
            'reference_bone_within_2mm_of_prior_bone': round(float((dist_mm[ref_bone] <= 2.0).mean()), 4) if ref_bone.any() else None,
            'reference_bone_within_5mm_of_prior_bone': round(float((dist_mm[ref_bone] <= 5.0).mean()), 4) if ref_bone.any() else None,
            'missed_reference_bone_voxels': int(missed.sum()),
            'missed_reference_bone_distance_mm_p50_p95': [round(float(np.percentile(dist_mm[missed], q)), 3) for q in (50, 95)] if missed.any() else None,
            'labelled_non_bone_within_2mm_of_prior_bone': round(float((dist_mm[labelled & ~ref_bone] <= 2.0).mean()), 4) if (labelled & ~ref_bone).any() else None,
            'sections_without_prior_bone': int(sum(1 for zz in z if not chans['bone'][:, :, zz].any())),
        }
        return out

    coverage_report = {
        'slices_with_any_ct_field_of_view': int((in_field > 0).sum()),
        'whole_block': stratum(list(range(k_first, k_first + nk))),
        'primary_training_slices': stratum(primary),
        'band_scoring_slices': stratum(scoring),
    }

    report = {
        'id': 'cryo-ct-prior-v2-block%d' % man['block']['region'], 'date': time.strftime('%Y-%m-%d'),
        'prior_version': 2, 'block': man['block'],
        'inputs': {
            'prior_map_v2': str(MAP_V2.relative_to(ROOT)), 'prior_map_v2_sha256': sha256_file(MAP_V2),
            'prior_map_v1': str(MAP_V1.relative_to(ROOT)), 'prior_map_v1_sha256': sha256_file(MAP_V1),
            'transform': str(TRANSFORM.relative_to(ROOT)), 'transform_sha256': sha256_file(TRANSFORM),
            'totalseg': str(TS.relative_to(ROOT)), 'totalseg_sha256': sha256_file(TS),
            'moose': {t: {'file': str(moose_path(t).relative_to(ROOT)), 'sha256': sha256_file(moose_path(t))} for t in MOOSE_TASKS},
            'skellytour': str(SKELLY.relative_to(ROOT)), 'skellytour_sha256': sha256_file(SKELLY),
            'skellytour_manifest_sha256': sha256_file(SKELLY_MANIFEST), 'skellytour_plan_sha256': sha256_file(SKELLY_PLAN),
            'skellytour_crop_ij': sk_plan['crop'],
            'coverage_mask': str(COVER.relative_to(ROOT)), 'coverage_mask_sha256': sha256_file(COVER),
            'block_manifest_sha256': sha256_file(block / 'manifest.json'),
            'tissue_classes_sha256': sha256_file(block / 'tissue-classes.nii.gz'),
            'bands': str(BANDS.relative_to(ROOT)), 'bands_sha256': sha256_file(BANDS),
            'v1_prior_sha256': sha256_file(v1_path) if v1_path.exists() else None,
        },
        'outputs': outputs,
        'output_dir_is_block': out_dir.resolve() == block.resolve(),
        'channels': [{'channel': i, 'name': c, **outputs[c]} for i, c in enumerate(CHANNELS)],
        'method': {
            'vote': pmap2['vote'], 'sources': pmap2['sources'], 'resampling': pmap2['resampling'],
            'distance': f'in-plane Euclidean distance to the nearest consensus-bone voxel of the same section, spacing ({sx}, {sy}) mm, clipped at {DIST_MAX_MM} mm, uint8 round(255 * d / {DIST_MAX_MM}); 255 in a section without consensus bone',
            'placement': pmap2['placement'],
        },
        'ct_grid': ct_stats,
        'coverage': coverage_report,
        'limits': pmap2['limits'] + [
            'prior_recall_of_reference is the fraction of Denver reference voxels of a class that the placed prior also calls that class; it mixes segmentation difference, placement error and posture, and separates none of them',
            'prior_on_labelled_other_tissue_fraction counts prior voxels of a class that fall on a Denver label of another class; prior voxels on ignore are counted apart because the tissue there is unlabelled, not negative',
            'the version 1 columns are the same measurement on data/derived/nlm-vhf/cryosections/block2/ct-prior-tissue.nii.gz; they compare two inputs, not two results',
        ],
        'seconds': round(time.time() - t0, 1),
    }
    rp = ROOT / ('generated/cryo-ct-prior-v2-block%d.json' % man['block']['region'])
    if not report['output_dir_is_block']:
        rp = out_dir / rp.name    # a scratch build describes itself and never replaces the canonical report
    rp.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'ok': True, 'report': str(rp.relative_to(ROOT)) if rp.is_relative_to(ROOT) else str(rp),
                      'consensus_bone_ct_voxels': ct_stats['bone_voxels']['consensus'],
                      'bone_recall_primary_v2_v1': [coverage_report['primary_training_slices']['bone']['prior_recall_of_reference'],
                                                    coverage_report['primary_training_slices']['bone'].get('v1_prior_recall_of_reference')],
                      'seconds': report['seconds']}))


if __name__ == '__main__':
    main()
