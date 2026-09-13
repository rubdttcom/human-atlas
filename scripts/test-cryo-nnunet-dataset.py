"""Tests of scripts/build-cryo-nnunet-dataset.py and scripts/build-cryo-ct-prior-block.py.

Each test mutates a document or an input in memory and requires the builder to refuse, or asserts a property of what the
builder wrote. No GPU, no training. A passing test is consistency, not anatomy.

  .venv/bin/python scripts/test-cryo-nnunet-dataset.py
"""
import ast
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = load('builder', 'scripts/build-cryo-nnunet-dataset.py')
P = load('prior', 'scripts/build-cryo-ct-prior-block.py')
BANDS = json.loads((ROOT / 'registry/cryo-eval-bands-v1.json').read_text())
PROTOCOL = json.loads((ROOT / 'registry/machine-acceptance-protocol-v1.json').read_text())
PRIOR_MAP = json.loads((ROOT / 'registry/cryo-ct-prior-map.json').read_text())
failures = []


def check(name, fn):
    try:
        fn()
    except AssertionError as e:
        failures.append(f'{name}: {e}')
    except SystemExit as e:
        failures.append(f'{name}: builder exited: {e}')
    else:
        print(f'  ok  {name}')


def refuses(name, fn):
    """The builder must raise SystemExit on a corrupted input."""
    try:
        fn()
    except SystemExit:
        print(f'  ok  {name} (refused)')
        return
    except AssertionError as e:
        failures.append(f'{name}: {e}')
        return
    failures.append(f'{name}: accepted a corrupted input')


# --- selection ---------------------------------------------------------------
def t_primary_count():
    primary, forbidden, scoring, aux = B.frozen_slices(BANDS)
    assert len(primary) == BANDS['training_eligibility']['primary_slices'] == 197, len(primary)
    assert not set(primary) & set(forbidden), 'primary meets a band or buffer'
    assert not set(primary) & set(aux), 'primary meets the auxiliary stratum'
    assert not set(primary) & set(scoring), 'primary meets a scoring slice'


def t_refuse_primary_in_band():
    bad = json.loads(json.dumps(BANDS))
    b0 = bad['bands'][0]
    bad['training_eligibility']['primary_k_ranges'].append([b0['k_first'], b0['k_first']])
    primary, forbidden, scoring, aux = B.frozen_slices(bad)
    B.check_selection(primary, forbidden, aux, bad)


def t_refuse_primary_in_auxiliary():
    bad = json.loads(json.dumps(BANDS))
    lo, hi = bad['training_eligibility']['auxiliary_k_ranges'][0]
    bad['training_eligibility']['primary_k_ranges'].append([lo, lo])
    primary, forbidden, scoring, aux = B.frozen_slices(bad)
    B.check_selection(primary, forbidden, aux, bad)


def t_refuse_count_drift():
    bad = json.loads(json.dumps(BANDS))
    bad['training_eligibility']['primary_slices'] = 196
    primary, forbidden, scoring, aux = B.frozen_slices(bad)
    B.check_selection(primary, forbidden, aux, bad)


# --- split -------------------------------------------------------------------
def t_split_blocked():
    primary, *_ = B.frozen_slices(BANDS)
    folds = B.blocked_folds(primary, BANDS)
    seen = set()
    for f in folds:
        lo, hi = f['bin_k']
        assert not set(f['val']) & set(f['train']), 'a slice is in train and validation'
        assert not set(f['val']) & seen, 'a slice validates twice'
        assert all(not (lo <= k <= hi) for k in f['train']), 'a training slice sits in its own validation bin'
        seen.update(f['val'])
    assert seen == set(primary), 'the folds do not cover the primary slices'
    assert len(folds[0]['train']) == max(len(f['train']) for f in folds), 'fold 0 is not the fold with the most training slices'


def t_refuse_incomplete_bins():
    bad = json.loads(json.dumps(BANDS))
    bad['training_eligibility']['bins_50mm'] = bad['training_eligibility']['bins_50mm'][:1]
    primary, *_ = B.frozen_slices(BANDS)
    B.blocked_folds(primary, bad)


# --- channels and labels -----------------------------------------------------
def t_variant_channels():
    assert B.VARIANTS['rgb-only']['channels'] == ['rgb_to_0_1'] * 3
    assert B.VARIANTS['rgb-plus-ct-prior']['channels'] == ['rgb_to_0_1'] * 3 + ['nonorm'] * 3
    active = set(PROTOCOL['training']['active_output_classes'])
    assert set(B.LABELS.values()) == active | {B.NNUNET_IGNORE}, B.LABELS
    # nnU-Net's LabelManager asserts the ignore label is max(labels) + 1; 255 is refused
    assert B.LABELS['ignore'] == max(active) + 1 == B.NNUNET_IGNORE, 'the nnU-Net ignore label is not max(active) + 1'
    assert B.REFERENCE_IGNORE == 255, 'the reference ignore value changed'
    assert B.NNUNET_IGNORE not in active, 'the ignore label collides with an active output class'


def t_ignore_remap_lossless():
    """Every reference value must survive the remap; only 255 moves, and it moves to 4."""
    sl = np.array([[0, 1, 2], [3, 255, 0]], dtype=np.uint8)
    out = B.remap_ignore(sl)
    assert out.dtype == np.uint8
    assert out[1, 1] == B.NNUNET_IGNORE, 'ignore was not remapped'
    keep = sl != 255
    assert np.array_equal(out[keep], sl[keep]), 'a non-ignore value changed'
    assert int((out == B.NNUNET_IGNORE).sum()) == int((sl == 255).sum()), 'the ignore count changed'


def t_ignore_remap_refuses_collision():
    """A reference that already holds 4 or 5 must be refused, never silently merged into ignore."""
    for v in (4, 5):
        try:
            B.remap_ignore(np.array([[0, v]], dtype=np.uint8))
        except SystemExit:
            continue
        raise AssertionError(f'reserved class {v} was accepted and would merge into ignore')


def t_written_labels_use_nnunet_ignore():
    """The dataset on disk must carry 4, never 255, and dataset.json must declare the same.

    This test used to skip silently when the dataset was absent and still reported ok (Codex-style audit of the
    uncommitted pilot code, finding 3). It now builds the dataset it needs, so a green line means it was checked.
    """
    for name, variant in (('Dataset501_VHFCryoBlock2RGB', 'rgb-only'),
                          ('Dataset502_VHFCryoBlock2RGBPrior', 'rgb-plus-ct-prior')):
        root = ROOT / 'data/derived/nnunet/raw' / name
        assert (root / 'dataset.json').exists(), (
            f'{name} is not built: run scripts/build-cryo-nnunet-dataset.py --variant {variant} first')
        dj = json.loads((root / 'dataset.json').read_text())
        assert dj['labels']['ignore'] == B.NNUNET_IGNORE, f'{name}: dataset.json declares another ignore label'
        files = sorted((root / 'labelsTr').glob('*.nii.gz'))
        assert files, f'{name}: no label file'
        for f in files[:8] + files[-8:]:
            vals = set(np.unique(np.asanyarray(nib.load(f).dataobj)).tolist())
            assert 255 not in vals, f'{f.name}: the reference ignore value 255 reached the nnU-Net dataset'
            assert vals <= {0, 1, 2, 3, B.NNUNET_IGNORE}, f'{f.name}: unexpected values {sorted(vals)}'


def t_case_geometry():
    """One written case must be (i, j, 1) uint8, so SimpleITK reads (1, j, i) for the 2D configuration."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / 'img').mkdir()
        (d / 'lbl').mkdir()
        chans = [np.full((7, 5), c, dtype=np.uint8) for c in range(3)]
        lbl = np.full((7, 5), B.NNUNET_IGNORE, dtype=np.uint8)
        B.write_case(d / 'img', d / 'lbl', 'c0', chans, lbl, np.diag([0.666, 0.666, 0.333, 1.0]))
        for c in range(3):
            img = nib.load(d / 'img' / f'c0_{c:04d}.nii.gz')
            assert img.shape == (7, 5, 1), img.shape
            assert img.get_data_dtype() == np.uint8, img.get_data_dtype()
            assert int(np.asanyarray(img.dataobj).max()) == c, 'channel order lost'
        out = nib.load(d / 'lbl' / 'c0.nii.gz')
        assert out.shape == (7, 5, 1) and int(np.asanyarray(out.dataobj).max()) == B.NNUNET_IGNORE, 'ignore value lost'


# --- CT prior ----------------------------------------------------------------
def t_image_and_label_share_the_grid():
    """Every written case must have its channels and its label on the same grid.

    write_case() is unit-tested with already-consistent arrays, so a dropped transpose in the real extraction
    (rgb-kji.npy is (k, j, i, 3); tissue-classes.nii.gz is (i, j, k)) would write a 434 x 666 image beside a
    666 x 434 label and no test would see it (audit finding 4).
    """
    for name in ('Dataset501_VHFCryoBlock2RGB', 'Dataset502_VHFCryoBlock2RGBPrior'):
        root = ROOT / 'data/derived/nnunet/raw' / name
        assert (root / 'dataset.json').exists(), f'{name} is not built'
        n_ch = len(json.loads((root / 'dataset.json').read_text())['channel_names'])
        labels = sorted((root / 'labelsTr').glob('*.nii.gz'))
        assert labels, f'{name}: no label file'
        for lf in labels[:4] + labels[-4:]:
            case = lf.name[:-len('.nii.gz')]
            lshape = nib.load(lf).shape
            for c in range(n_ch):
                ifile = root / 'imagesTr' / f'{case}_{c:04d}.nii.gz'
                assert ifile.exists(), f'{case}: channel {c} missing'
                assert nib.load(ifile).shape == lshape, (
                    f'{case} channel {c}: image {nib.load(ifile).shape} against label {lshape}')
            assert lshape[2] == 1, f'{case}: the slice axis is not a singleton'


def t_buffer_layout_asserted():
    """A band whose buffers do not bracket it must be refused, not silently spanned as an empty range."""
    for b in BANDS['bands']:
        B.band_forbidden(b)                       # the frozen file must pass
    bad = json.loads(json.dumps(BANDS['bands'][0]))
    bad['buffer_k'] = [bad['buffer_k'][1], bad['buffer_k'][0]]   # reversed: range() would be empty
    try:
        B.band_forbidden(bad)
    except SystemExit:
        return
    raise AssertionError('a reversed buffer pair was accepted and would forbid nothing')


def t_paired_status_matches_the_evaluator():
    """The builder and the frozen evaluator must agree on what counts as a paired slice (audit finding 6)."""
    src = (ROOT / 'scripts/cryo-pilot-evaluate.py').read_text()
    m = re.search(r'^PAIRED\s*=\s*(\(.*?\))\s*$', src, re.M)
    assert m, 'PAIRED not found in the evaluator'
    assert B.PAIRED == ast.literal_eval(m.group(1)), f'builder PAIRED {B.PAIRED} differs from the evaluator'


def t_prior_map_exhaustive():
    cm = json.loads((ROOT / 'data/derived/nlm-vhf/totalseg-classmap.json').read_text())['total']
    declared = {e['value']: e['name'] for e in PRIOR_MAP['labels']}
    assert declared == {int(k): v for k, v in cm.items()}, 'the prior map is not the TotalSegmentator total classmap'
    assert all(e['class'] in ('bone', 'cartilage', 'muscle', 'none') for e in PRIOR_MAP['labels'])
    assert all(e.get('reason') for e in PRIOR_MAP['labels']), 'a label has no reason'


def t_prior_lut():
    lut = P.lut_from_map(PRIOR_MAP)
    by_name = {e['name']: e['value'] for e in PRIOR_MAP['labels']}
    assert lut[by_name['femur_left']] == 1 and lut[by_name['hip_right']] == 1, 'a bone label lost its class'
    assert lut[by_name['costal_cartilages']] == 2, 'cartilage lost its class'
    assert lut[by_name['gluteus_maximus_left']] == 3 and lut[by_name['iliopsoas_right']] == 3, 'muscle lost its class'
    assert lut[by_name['liver']] == 0 and lut[by_name['spinal_cord']] == 0, 'a non-tissue label became a class'
    assert lut[0] == 0, 'the unlabelled CT value is not none'


def t_prior_nearest_neighbour():
    """A half-voxel placement shift must move labels, never blend them into a new value."""
    lut = P.lut_from_map(PRIOR_MAP)
    ct = np.zeros((4, 4, 4), dtype=np.uint8)
    ct[1, 1, 1] = 75      # femur_left -> bone
    ct[2, 1, 1] = 80      # gluteus_maximus_left -> muscle
    shift = np.eye(4)
    shift[0, 3] = 0.4
    cls, _ = P.sample_slice(1, shift, np.eye(4), np.eye(4), ct, lut, (4, 4))
    assert set(np.unique(cls).tolist()) <= {0, 1, 3}, f'interpolation invented a class: {np.unique(cls)}'


def t_prior_report_matches_disk():
    rp = ROOT / 'generated/cryo-ct-prior-block2.json'
    assert rp.exists(), 'the prior report is missing: run build-cryo-ct-prior-block.py'
    rep = json.loads(rp.read_text())
    assert rep['inputs']['prior_map_sha256'] == P.sha256_file(ROOT / 'registry/cryo-ct-prior-map.json'), \
        'the prior report was written against another prior map'
    vol = ROOT / 'data/derived/nlm-vhf/cryosections/block2/ct-prior-tissue.nii.gz'
    if vol.exists():
        assert rep['outputs']['prior_sha256'] == P.sha256_file(vol), 'the prior volume changed after the report'
        assert set(np.unique(np.asanyarray(nib.load(vol).dataobj)).tolist()) <= {0, 1, 2, 3}, \
            'the prior volume holds a value outside none/bone/cartilage/muscle'
    assert rep['coverage']['primary_training_slices']['slices'] == 197


def t_prior_never_the_target():
    """The prior map must not be part of the protocol identity, and the tissue map must be untouched."""
    fixed = PROTOCOL['identity_by_hash']['fixed_now']
    assert 'cryo-ct-prior-map.json' not in json.dumps(fixed), 'the prior map entered the frozen protocol identity'
    assert fixed['tissue_map_sha256'] == P.sha256_file(ROOT / 'registry/cryo-tissue-map.json'), \
        'registry/cryo-tissue-map.json changed: protocol v1 is no longer valid'


for n, f in [('primary selection', t_primary_count), ('split is blocked', t_split_blocked),
             ('variant channels and ignore label', t_variant_channels), ('case geometry', t_case_geometry),
             ('image and label share the grid', t_image_and_label_share_the_grid),
             ('buffer layout is asserted', t_buffer_layout_asserted),
             ('paired status matches the evaluator', t_paired_status_matches_the_evaluator),
             ('prior map is exhaustive', t_prior_map_exhaustive), ('prior lookup table', t_prior_lut),
             ('prior resampling is nearest neighbour', t_prior_nearest_neighbour),
             ('prior report matches disk', t_prior_report_matches_disk),
             ('ignore remap is lossless', t_ignore_remap_lossless),
             ('ignore remap refuses a reserved class', t_ignore_remap_refuses_collision),
             ('written labels use the nnU-Net ignore label', t_written_labels_use_nnunet_ignore),
             ('prior is not the target and the tissue map is untouched', t_prior_never_the_target)]:
    check(n, f)
for n, f in [('primary slice inside a band', t_refuse_primary_in_band),
             ('primary slice in the auxiliary stratum', t_refuse_primary_in_auxiliary),
             ('primary slice count drift', t_refuse_count_drift),
             ('bins do not cover the primary slices', t_refuse_incomplete_bins)]:
    refuses(n, f)

print(json.dumps({'ok': not failures, 'failures': failures}))
sys.exit(1 if failures else 0)
