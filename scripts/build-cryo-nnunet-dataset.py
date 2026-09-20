"""Build the nnU-Net v2 raw dataset of the cryosection pilot for one variant (plan B stage 2, step 5 of section 9.3).

Two variants, both 2D and both on the SAME slices and the SAME target:
  rgb-only           3 channels: R, G, B of the aligned photograph resampled on the Denver grid
  rgb-plus-ct-prior  6 channels: R, G, B plus three binary CT prior channels (bone, cartilage, muscle) from
                     registry/cryo-ct-prior-map.json applied to the fresh-CT TotalSegmentator labels and carried onto the
                     block grid by scripts/build-cryo-ct-prior-block.py. The prior is an input only: it never touches the
                     target, the reference or the metrics.
  rgb-plus-ct-prior --prior-version 2 (protocol version 2 runs, 2026-09-20): 7 channels: R, G, B plus the four
                     channels of registry/cryo-ct-prior-map-v2.json built by scripts/build-cryo-ct-prior-v2-block.py
                     (consensus bone, bone disagreement, in-plane distance to consensus bone as float32 0..1, TotalSegmentator
                     muscle). Dataset 503. The version 1 dataset (502) and its report are untouched.

Slice selection is the frozen one and is not a parameter: training uses exactly the primary eligibility of
registry/cryo-eval-bands-v1.json (197 paired slices). Band slices, their 10 mm buffers, the auxiliary stratum and the
never-sampled slices are refused here, so a dataset that the evaluator's training gate would reject cannot be built.
--slices bands writes the band slices to imagesTs for inference; they carry no label and never enter training.

Ignore encoding. The reference volume tissue-classes.nii.gz uses 255 for ignore and its hash is pinned by the protocol,
so it is never touched. nnU-Net refuses that value: LabelManager asserts the ignore label equals max(labels) + 1. The
label files of the nnU-Net dataset therefore carry 4 where the reference carries 255, and dataset.json declares
{background 0, bone 1, cartilage 2, muscle 3, ignore 4}. Inside this derived dataset the value 4 means ignore and
nothing else: the registry meaning of 4 (ligament-tendon) is not declared here and the builder refuses any source volume
that already holds 4 or 5, so the remap cannot merge a real class into the ignore label. The network still outputs only
classes 0 to 3, which is what the evaluator's prediction gate allows.

The internal split is frozen and spatially blocked by the 50 mm bins of the bands file: fold f validates bin f. The
earlier wording here claimed that two neighbouring slices never straddle train and validation. That is false and the
Codex audit of 1af1c60 measured it: the primary slices run continuously across a bin boundary, so in all four folds the
minimum distance between a training slice and a validation slice is one slice, 0.333 mm. What the blocking does give is
that validation never samples INSIDE a training bin, which removes the shuffled-slice leak but not the boundary pair.
The bands and their 10 mm buffers are a different mechanism and are unaffected: they are never sampled at all. Fold 0 is trained because bin 0 holds the fewest primary slices
and therefore leaves the most for training (187 of 197); the rule is stated here before any score exists and is not a
choice between measured results. Inference must use checkpoint_final, so the validation fold reports and never selects;
the result that is graded is the frozen band prediction, not this split.

  .venv/bin/python scripts/build-cryo-nnunet-dataset.py --block data/derived/nlm-vhf/cryosections/block2 \
      --variant rgb-only --out data/derived/nnunet/raw [--slices train|bands] [--selftest]

Writes the dataset tree, splits_final.json, and generated/cryo-nnunet-dataset-block2-<variant>.json (the provenance the
training manifest copies). Nothing here is anatomy.
"""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BANDS = ROOT / 'registry/cryo-eval-bands-v1.json'
PROTOCOL = ROOT / 'registry/machine-acceptance-protocol-v1.json'
PROTOCOL_V2 = ROOT / 'registry/machine-acceptance-protocol-v2.json'   # named by the report of a prior-version 2 build
PRIOR_MAP = ROOT / 'registry/cryo-ct-prior-map.json'
PRIOR_MAP_V2 = ROOT / 'registry/cryo-ct-prior-map-v2.json'
PRIOR_V2_CHANNELS = ('bone', 'bone-disagreement', 'bone-distance', 'muscle')   # order of registry/cryo-ct-prior-map-v2.json
PRIOR_V2_DISTANCE_SCALE = 255.0   # the distance channel is uint8 0..255 on disk and float32 0..1 in the dataset
REFERENCE_IGNORE = 255       # the value in tissue-classes.nii.gz, pinned by the protocol
NNUNET_IGNORE = 4            # nnU-Net asserts ignore == max(labels) + 1; used only inside the derived dataset
DUMMY_SLICE_SPACING_MM = 999.0   # nnU-Net's 2D convention: the singleton axis must have the largest spacing
PAIRED = ('usable', 'usable-flagged')   # must equal scripts/cryo-pilot-evaluate.py PAIRED; asserted by the tests
LABELS = {'background': 0, 'bone': 1, 'cartilage': 2, 'muscle': 3, 'ignore': NNUNET_IGNORE}
VARIANTS = {
    'rgb-only': {'dataset_id': 501, 'name': 'Dataset501_VHFCryoBlock2RGB',
                 'channels': ['rgb_to_0_1'] * 3},
    'rgb-plus-ct-prior': {'dataset_id': 502, 'name': 'Dataset502_VHFCryoBlock2RGBPrior',
                          'channels': ['rgb_to_0_1'] * 3 + ['nonorm'] * 3},
}
# the same variant with the version 2 prior channels; a different dataset so nothing of 502 is overwritten
PRIOR_V2_SPEC = {'dataset_id': 503, 'name': 'Dataset503_VHFCryoBlock2RGBPriorV2',
                 'channels': ['rgb_to_0_1'] * 3 + ['nonorm'] * len(PRIOR_V2_CHANNELS)}


def variant_spec(variant, prior_version):
    if variant == 'rgb-plus-ct-prior' and prior_version == 2:
        return PRIOR_V2_SPEC
    if prior_version == 2:
        raise SystemExit(json.dumps({'ok': False, 'error': 'prior version 2 exists only for rgb-plus-ct-prior'}))
    return VARIANTS[variant]


def report_stem(variant, prior_version):
    """generated/cryo-nnunet-dataset-block2-<variant>[-v2]: the training manifest writer reads the same name."""
    return f'cryo-nnunet-dataset-block2-{variant}' + ('-v2' if prior_version == 2 else '')


def sha256_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def expand(ranges):
    return sorted({k for lo, hi in ranges for k in range(lo, hi + 1)})


def band_forbidden(b):
    """Buffer + band + buffer for one band, with the layout asserted instead of assumed.

    buffer_k is [[before_lo, before_hi], [after_lo, after_hi]]. The frozen evaluator spans it as
    range(buffer_k[0][0], buffer_k[1][1] + 1), which is only the band plus its buffers when the two buffers really
    bracket the band and are contiguous with it. A reversed or detached pair would make that range EMPTY and the
    overlap check would then pass while checking nothing, so the layout is asserted here.
    """
    (b0, b1), (a0, a1) = b['buffer_k']
    lo, hi = b['k_first'], b['k_last']
    if not (b0 <= b1 == lo - 1 and hi + 1 == a0 <= a1):
        raise SystemExit(json.dumps({'ok': False, 'error':
            f'band {lo}..{hi} has buffers {b["buffer_k"]} that do not bracket it contiguously'}))
    return range(b0, a1 + 1)


def frozen_slices(bands):
    """primary training slices, forbidden slices (band + buffer), band scoring slices, auxiliary slices."""
    te = bands['training_eligibility']
    primary = expand(te['primary_k_ranges'])
    aux = expand(te['auxiliary_k_ranges'])
    forbidden, scoring = set(), []
    for b in bands['bands']:
        forbidden.update(band_forbidden(b))
        scoring.extend(range(b['k_first'], b['k_last'] + 1))
    return primary, sorted(forbidden), sorted(set(scoring)), aux


def check_selection(primary, forbidden, aux, bands):
    """The selection rules of the protocol, asserted here so an unusable dataset cannot be written."""
    p, f, a = set(primary), set(forbidden), set(aux)
    if p & f:
        raise SystemExit(json.dumps({'ok': False, 'error': f'{len(p & f)} primary slices lie in a band or buffer'}))
    if p & a:
        raise SystemExit(json.dumps({'ok': False, 'error': f'{len(p & a)} primary slices lie in the auxiliary stratum'}))
    if len(p) != bands['training_eligibility']['primary_slices']:
        raise SystemExit(json.dumps({'ok': False, 'error': 'primary slice count differs from the bands file'}))


def blocked_folds(primary, bands):
    """Frozen split: fold f validates the 50 mm bin f of the bands file. Neighbours never straddle."""
    bins = bands['training_eligibility']['bins_50mm']
    folds, used = [], set()
    for b in bins:
        lo, hi = b['k']
        val = [k for k in primary if lo <= k <= hi]
        if not val:
            continue
        used.update(val)
        folds.append({'bin_k': [lo, hi], 'val': val, 'train': [k for k in primary if k not in set(val)]})
    if used != set(primary):
        raise SystemExit(json.dumps({'ok': False, 'error': 'the 50 mm bins do not cover every primary slice'}))
    return folds


def remap_ignore(sl):
    """Reference 255 -> nnU-Net 4. Refuses a slice that already holds 4 or 5, so no real class is merged into ignore."""
    clash = sorted(set(np.unique(sl).tolist()) & {4, 5})
    if clash:
        raise SystemExit(json.dumps({'ok': False, 'error': f'the reference holds reserved class {clash}: the ignore remap would merge it'}))
    out = sl.astype(np.uint8, copy=True)
    out[sl == REFERENCE_IGNORE] = NNUNET_IGNORE
    return out


def write_case(img_dir, lbl_dir, case, chans, label, affine):
    for c, arr in enumerate(chans):
        # uint8 for colour and binary channels; a float32 channel (the version 2 distance) keeps its dtype
        dt = np.float32 if arr.dtype == np.float32 else np.uint8
        nib.save(nib.Nifti1Image(arr[:, :, None].astype(dt, copy=False), affine, dtype=dt), img_dir / f'{case}_{c:04d}.nii.gz')
    if label is not None:
        nib.save(nib.Nifti1Image(label[:, :, None], affine, dtype=np.uint8), lbl_dir / f'{case}.nii.gz')


def selftest():
    bands = json.loads(BANDS.read_text())
    primary, forbidden, scoring, aux = frozen_slices(bands)
    check_selection(primary, forbidden, aux, bands)
    folds = blocked_folds(primary, bands)
    assert len(primary) == 197, f'primary count {len(primary)}'
    assert not (set(primary) & set(scoring)), 'a band slice reached the training set'
    seen = set()
    for f in folds:
        assert not (set(f['val']) & set(f['train'])), 'a slice is in train and validation of the same fold'
        assert not (set(f['val']) & seen), 'a slice validates in two folds'
        seen.update(f['val'])
        lo, hi = f['bin_k']
        for k in f['train']:
            assert not (lo <= k <= hi), 'a training slice lies inside its own validation bin'
    assert seen == set(primary), 'the folds do not cover the primary slices'
    print(json.dumps({'selftest': 'ok', 'primary': len(primary), 'folds': len(folds),
                      'val_per_fold': [len(f['val']) for f in folds]}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--block', required=True)
    ap.add_argument('--variant', choices=sorted(VARIANTS), required=True)
    ap.add_argument('--out', default='data/derived/nnunet/raw')
    ap.add_argument('--slices', choices=['train', 'bands'], default='train')
    ap.add_argument('--prior-version', type=int, choices=[1, 2], default=1,
                    help='rgb-plus-ct-prior only: 1 = the version 1 prior of dataset 502, 2 = registry/cryo-ct-prior-map-v2.json, dataset 503')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    t0 = time.time()

    block = Path(a.block)
    man = json.loads((block / 'manifest.json').read_text())
    bands = json.loads(BANDS.read_text())
    protocol_path = PROTOCOL_V2 if a.prior_version == 2 else PROTOCOL
    protocol = json.loads(protocol_path.read_text())
    spec = variant_spec(a.variant, a.prior_version)

    primary, forbidden, scoring, aux = frozen_slices(bands)
    check_selection(primary, forbidden, aux, bands)
    folds = blocked_folds(primary, bands)
    ks = primary if a.slices == 'train' else scoring

    nk, nj, ni = man['grid']['shape_kji3'][:3]
    k_first = man['block']['k_first']
    status = {r['k']: r['status'] for r in man['per_slice']}
    paired = PAIRED   # the evaluator's own constant; the protocol declares no paired_status key

    rgb = np.load(block / 'rgb-kji.npy', mmap_mode='r')          # (k, j, i, 3)
    tissue_img = nib.load(block / 'tissue-classes.nii.gz')        # (i, j, k)
    tissue = np.asanyarray(tissue_img.dataobj)
    present = set(np.unique(tissue).tolist())
    allowed = set(protocol['training']['active_output_classes']) | {REFERENCE_IGNORE}
    if not present <= allowed:
        raise SystemExit(json.dumps({'ok': False, 'error': f'tissue classes outside {sorted(allowed)}: {sorted(present - allowed)}'}))

    prior = None          # version 1: one class volume, three binary channels
    prior_v2 = None       # version 2: four channel volumes in the order of PRIOR_V2_CHANNELS
    if a.variant == 'rgb-plus-ct-prior' and a.prior_version == 1:
        pp = block / 'ct-prior-tissue.nii.gz'
        if not pp.exists():
            raise SystemExit(json.dumps({'ok': False, 'error': f'{pp} missing: run build-cryo-ct-prior-block.py first'}))
        prior = np.asanyarray(nib.load(pp).dataobj)
        if prior.shape != tissue.shape:
            raise SystemExit(json.dumps({'ok': False, 'error': 'prior and reference shapes differ'}))
    elif a.variant == 'rgb-plus-ct-prior' and a.prior_version == 2:
        pmap2 = json.loads(PRIOR_MAP_V2.read_text())
        if tuple(c['name'] for c in pmap2['channels']) != PRIOR_V2_CHANNELS:
            raise SystemExit(json.dumps({'ok': False, 'error': 'the version 2 prior map does not list the channels this builder writes'}))
        rep2_path = ROOT / 'generated/cryo-ct-prior-v2-block2.json'
        if not rep2_path.exists():
            raise SystemExit(json.dumps({'ok': False, 'error': f'{rep2_path} missing: run build-cryo-ct-prior-v2-block.py first'}))
        rep2 = json.loads(rep2_path.read_text())
        if rep2['inputs']['prior_map_v2_sha256'] != sha256_file(PRIOR_MAP_V2):
            raise SystemExit(json.dumps({'ok': False, 'error': 'the version 2 prior report was written against another prior map'}))
        prior_v2 = []
        for c in PRIOR_V2_CHANNELS:
            pp = block / f'ct-prior-v2-{c}.nii.gz'
            if not pp.exists():
                raise SystemExit(json.dumps({'ok': False, 'error': f'{pp} missing: run build-cryo-ct-prior-v2-block.py first'}))
            if rep2['outputs'][c]['sha256'] != sha256_file(pp):
                raise SystemExit(json.dumps({'ok': False, 'error': f'{pp.name} changed after its report was written'}))
            vol = np.asanyarray(nib.load(pp).dataobj)
            if vol.shape != tissue.shape:
                raise SystemExit(json.dumps({'ok': False, 'error': f'prior channel {c} and reference shapes differ'}))
            if not np.allclose(nib.load(pp).affine, tissue_img.affine, atol=1e-6):
                raise SystemExit(json.dumps({'ok': False, 'error': f'prior channel {c} is not on the reference affine'}))
            if c != 'bone-distance' and not set(np.unique(vol).tolist()) <= {0, 1}:
                raise SystemExit(json.dumps({'ok': False, 'error': f'prior channel {c} is not binary'}))
            prior_v2.append(vol)

    # A 2D case is one slice stored with a singleton last axis; the reader transposes it to (1, j, i).
    # The singleton axis carries the dummy spacing 999 mm, nnU-Net's own convention for a 2D dataset: the
    # experiment planner puts the axis with the LARGEST spacing first, and the real through-plane spacing
    # (0.333 mm) is the smallest of the three, so it would be reordered into the middle and the planner would
    # cut one-pixel strips instead of slices. The dummy value never leaves this dataset: the graded volume is
    # rebuilt on the reference affine by scripts/assemble-cryo-prediction.py.
    sx, sy, sz = man['grid']['spacing_mm_ijk']
    affine = np.diag([sx, sy, DUMMY_SLICE_SPACING_MM, 1.0])

    root = ROOT / a.out / spec['name']
    img_dir = root / ('imagesTr' if a.slices == 'train' else 'imagesTs')
    lbl_dir = root / 'labelsTr'
    if img_dir.exists():
        shutil.rmtree(img_dir)
    img_dir.mkdir(parents=True)
    if a.slices == 'train':
        if lbl_dir.exists():
            shutil.rmtree(lbl_dir)
        lbl_dir.mkdir(parents=True)

    cases, skipped = [], []
    for k in ks:
        if status.get(k) not in paired:
            skipped.append({'k': k, 'status': status.get(k)})
            continue
        z = k - k_first
        sl = np.ascontiguousarray(rgb[z])                        # (j, i, 3)
        chans = [np.ascontiguousarray(sl[:, :, c].T) for c in range(3)]   # -> (i, j)
        if prior is not None:
            for v in (1, 2, 3):
                chans.append((prior[:, :, z] == v).astype(np.uint8))
        if prior_v2 is not None:
            for c, vol in zip(PRIOR_V2_CHANNELS, prior_v2):
                sl2 = np.ascontiguousarray(vol[:, :, z])
                if c == 'bone-distance':
                    chans.append((sl2.astype(np.float32) / PRIOR_V2_DISTANCE_SCALE).astype(np.float32))
                else:
                    chans.append(sl2.astype(np.uint8))
        label = remap_ignore(tissue[:, :, z]) if a.slices == 'train' else None
        case = f'block2_k{k:05d}'
        write_case(img_dir, lbl_dir, case, chans, label, affine)
        cases.append(case)

    doc = {'channel_names': {str(i): n for i, n in enumerate(spec['channels'])},
           'labels': LABELS, 'numTraining': len(cases), 'file_ending': '.nii.gz',
           'overwrite_image_reader_writer': 'NibabelIOWithReorient'}
    if a.slices == 'train':
        (root / 'dataset.json').write_text(json.dumps(doc, indent=1) + '\n')
        splits = [{'train': [f'block2_k{k:05d}' for k in f['train'] if status.get(k) in paired],
                   'val': [f'block2_k{k:05d}' for k in f['val'] if status.get(k) in paired]} for f in folds]
        (root / 'splits_final.json').write_text(json.dumps(splits, indent=1) + '\n')

    report = {
        'id': report_stem(a.variant, a.prior_version),
        'date': time.strftime('%Y-%m-%d'), 'variant': a.variant, 'slices': a.slices,
        'prior_version': a.prior_version if a.variant == 'rgb-plus-ct-prior' else None,
        'dataset_id': spec['dataset_id'], 'dataset_name': spec['name'],
        'channels': spec['channels'],
        'channel_meaning': (['photograph R', 'photograph G', 'photograph B'] +
                            (['CT prior bone', 'CT prior cartilage', 'CT prior muscle'] if prior is not None else []) +
                            (['CT prior v2 consensus bone', 'CT prior v2 bone disagreement',
                              'CT prior v2 in-plane distance to consensus bone (float32 0..1 = mm / 15)',
                              'CT prior v2 muscle (TotalSegmentator)'] if prior_v2 is not None else [])),
        'cases': len(cases), 'case_ids': cases,
        'training_slices_k': [int(c.split('_k')[1]) for c in cases] if a.slices == 'train' else [],
        'skipped_unpaired': skipped,
        'selection': {
            'rule': 'primary eligibility of the bands file, paired slices only; bands, buffers, auxiliary and never-sampled refused',
            'primary_slices': len(primary), 'band_scoring_slices': len(scoring), 'auxiliary_slices': len(aux),
            'bands_sha256': sha256_file(BANDS),
        },
        'split': {'kind': 'frozen, blocked by the 50 mm bins of the bands file',
                  'boundary_limit': ('a training slice and a validation slice can be adjacent across a bin boundary '
                                     '(minimum distance 1 slice, 0.333 mm, in all four folds); the blocking stops a '
                                     'shuffled-slice split, not the boundary pair. The graded bands keep their 10 mm '
                                     'buffers and are never sampled.'),
                  'folds': [{'bin_k': f['bin_k'], 'val': len(f['val']), 'train': len(f['train'])} for f in folds],
                  'fold_trained': 0,
                  'fold_0_rationale': ('bin 0 holds the fewest primary slices, so fold 0 leaves the most for training; '
                                       'fixed before any score existed'),
                  'inference_checkpoint': 'checkpoint_final: the validation fold reports, it never selects'},
        'inputs': {
            'block_manifest_sha256': sha256_file(block / 'manifest.json'),
            'rgb_sha256': man['outputs']['rgb_sha256'],
            'tissue_classes_sha256': sha256_file(block / 'tissue-classes.nii.gz'),
            'tissue_map_sha256': protocol['identity_by_hash']['fixed_now']['tissue_map_sha256'],
            'protocol': str(protocol_path.relative_to(ROOT)), 'protocol_version': protocol['version'],
            'protocol_sha256': sha256_file(protocol_path),
        },
        'slice_axis_spacing': {
            'stored_mm': DUMMY_SLICE_SPACING_MM, 'true_through_plane_mm': sz,
            'reason': ('nnU-Net orders the axes by spacing and puts the largest first; with the true 0.333 mm the '
                       'singleton axis was reordered into the middle and the 2D planner produced a [1, 704] patch, '
                       'one-pixel strips instead of slices'),
            'scope': 'the derived nnU-Net cases only; the graded volume is rebuilt on the reference affine',
        },
        'ignore_encoding': {
            'reference_value': REFERENCE_IGNORE, 'nnunet_value': NNUNET_IGNORE,
            'reason': 'nnU-Net asserts the ignore label equals max(labels) + 1 and refuses 255',
            'scope': 'the derived nnU-Net label files only; tissue-classes.nii.gz and its pinned hash are untouched',
            'collision': 'the registry meaning of 4 (ligament-tendon) is not declared in this dataset; the builder refuses a source volume that already holds 4 or 5',
        },
        'limits': [
            'the prior channels are an input, never a target: the reference stays the Denver original labels through the tissue map',
            'the ignore label is 4 inside the nnU-Net dataset and 255 in the reference; the two encodings must never be compared directly',
            'a 2D configuration sees one slice at a time; no through-plane context',
            'the frozen split reports only; the graded result is the band prediction',
        ],
        'seconds': round(time.time() - t0, 1),
    }
    if prior is not None:
        report['inputs']['ct_prior_sha256'] = sha256_file(block / 'ct-prior-tissue.nii.gz')
        report['inputs']['ct_prior_map_sha256'] = sha256_file(PRIOR_MAP)
        report['prior_coverage'] = json.loads((ROOT / 'generated/cryo-ct-prior-block2.json').read_text())['coverage']
    if prior_v2 is not None:
        report['inputs']['ct_prior_v2'] = {c: {'file': f'ct-prior-v2-{c}.nii.gz', 'sha256': sha256_file(block / f'ct-prior-v2-{c}.nii.gz')}
                                           for c in PRIOR_V2_CHANNELS}
        report['inputs']['ct_prior_map_v2_sha256'] = sha256_file(PRIOR_MAP_V2)
        report['inputs']['ct_prior_v2_report'] = str(rep2_path.relative_to(ROOT))
        report['inputs']['ct_prior_v2_report_sha256'] = sha256_file(rep2_path)
        report['prior_coverage'] = rep2['coverage']
        report['prior_distance_channel'] = {'on_disk': 'uint8 0..255', 'in_dataset': 'float32 value / 255 = mm / 15, clipped',
                                            'reason': 'nnU-Net applies no normalisation to a nonorm channel; the colour channels are 0..1, so the distance is scaled to the same range'}
    # same rule as the prior builder: a build into a scratch directory describes that build, and never
    # replaces the committed report of the canonical one
    suffix = '' if a.slices == 'train' else '-bands'
    canonical_out = ROOT / 'data/derived/nnunet/raw'
    is_canonical = (ROOT / a.out).resolve() == canonical_out.resolve() if not Path(a.out).is_absolute() else Path(a.out).resolve() == canonical_out.resolve()
    stem = report_stem(a.variant, a.prior_version)
    rp = (ROOT / f'generated/{stem}{suffix}.json' if is_canonical else root.parent / f'{stem}{suffix}.json')
    report['is_canonical_build'] = is_canonical
    # relative to the repository when it is inside it: an absolute path would publish the machine's
    # home directory and user name in a public repository, and says nothing a reader needs
    report['output_root'] = str(root.parent.relative_to(ROOT)) if root.parent.is_relative_to(ROOT) else '(outside the repository)'
    rp.write_text(json.dumps(report, indent=1) + '\n')
    shown = rp.relative_to(ROOT) if rp.is_relative_to(ROOT) else rp   # a scratch build reports outside the repo
    print(json.dumps({'ok': True, 'dataset': str(root), 'cases': len(cases), 'skipped': len(skipped),
                      'report': str(shown), 'seconds': report['seconds']}))


if __name__ == '__main__':
    main()
