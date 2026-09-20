"""Tests of scripts/build-cryo-nnunet-dataset.py, scripts/build-cryo-ct-prior-block.py and scripts/build-cryo-ct-prior-v2-block.py.

Each test mutates a document or an input in memory and requires the builder to refuse, or asserts a property of what the
builder wrote. No GPU, no training. A passing test is consistency, not anatomy.

  .venv/bin/python scripts/test-cryo-nnunet-dataset.py
"""
import ast
import importlib.util
import json
import re
import subprocess
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

    Kept as a check of the committed dataset when it is present. The property itself is proved by
    t_builder_output_from_a_real_run, which runs the builder instead of reading whatever is on disk.
    """
    names = [n for n in ('Dataset501_VHFCryoBlock2RGB', 'Dataset502_VHFCryoBlock2RGBPrior')
             if (ROOT / 'data/derived/nnunet/raw' / n / 'dataset.json').exists()]
    if not names:
        return                       # the built dataset is optional here; the builder test is the real one
    for name in names:
        root = ROOT / 'data/derived/nnunet/raw' / name
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
def t_builder_output_from_a_real_run():
    """Run the real builder into a temp tree and check what it wrote, channel by channel.

    The earlier test read the shapes of eight files that happened to be on disk, so a stale dataset hid a
    regression of the extraction and nothing checked the CONTENT or the affine (Codex audit of 1af1c60). This
    runs scripts/build-cryo-nnunet-dataset.py itself and compares every channel and every target against the
    sources, on an asymmetric grid where a transpose cannot pass unnoticed.
    """
    block = ROOT / 'data/derived/nlm-vhf/cryosections/block2'
    if not (block / 'rgb-kji.npy').exists():
        raise AssertionError('block2 is not on disk: the builder cannot be exercised')
    man = json.loads((block / 'manifest.json').read_text())
    nk, nj, ni = man['grid']['shape_kji3'][:3]
    assert ni != nj, 'the block grid is square, so a transpose would be invisible to this test'
    with tempfile.TemporaryDirectory() as d:
        cmd = [sys.executable, str(ROOT / 'scripts/build-cryo-nnunet-dataset.py'),
               '--block', str(block), '--variant', 'rgb-plus-ct-prior', '--slices', 'train', '--out', d]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f'the builder failed: {r.stderr[-400:]}'
        root = Path(d) / B.VARIANTS['rgb-plus-ct-prior']['name']
        dj = json.loads((root / 'dataset.json').read_text())
        assert dj['labels']['ignore'] == B.NNUNET_IGNORE
        assert len(dj['channel_names']) == 6, dj['channel_names']

        rgb = np.load(block / 'rgb-kji.npy', mmap_mode='r')
        tissue = np.asanyarray(nib.load(block / 'tissue-classes.nii.gz').dataobj)
        prior = np.asanyarray(nib.load(block / 'ct-prior-tissue.nii.gz').dataobj)
        k_first = man['block']['k_first']
        cases = sorted((root / 'labelsTr').glob('*.nii.gz'))
        assert len(cases) == 197, f'{len(cases)} cases written, expected 197'
        for lf in cases[:3] + cases[len(cases) // 2:len(cases) // 2 + 2] + cases[-3:]:
            case = lf.name[:-len('.nii.gz')]
            k = int(case.split('_k')[1])
            z = k - k_first
            lab = np.squeeze(np.asanyarray(nib.load(lf).dataobj))
            want = tissue[:, :, z].copy()
            want[want == 255] = B.NNUNET_IGNORE
            assert lab.shape == (ni, nj), f'{case}: label shape {lab.shape} against {(ni, nj)}'
            assert np.array_equal(lab, want), f'{case}: the target is not the tissue classes with ignore remapped'
            for c in range(3):
                got = np.squeeze(np.asanyarray(nib.load(root / 'imagesTr' / f'{case}_{c:04d}.nii.gz').dataobj))
                assert np.array_equal(got, rgb[z][:, :, c].T), f'{case}: colour channel {c} is not the transposed source'
            for c, v in enumerate((1, 2, 3), start=3):
                got = np.squeeze(np.asanyarray(nib.load(root / 'imagesTr' / f'{case}_{c:04d}.nii.gz').dataobj))
                assert np.array_equal(got, (prior[:, :, z] == v).astype(np.uint8)), f'{case}: prior channel {c} wrong'
            img0 = nib.load(root / 'imagesTr' / f'{case}_0000.nii.gz')
            assert np.allclose(img0.affine, np.diag([0.666, 0.666, B.DUMMY_SLICE_SPACING_MM, 1.0]), atol=1e-3), \
                f'{case}: the 2D case affine is not the dataset grid'


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
             ('builder output from a real run', t_builder_output_from_a_real_run),
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


# --- prior version 2 (protocol version 2 runs, 2026-09-20) ---------------------------------------------------------
P2 = load('prior_v2', 'scripts/build-cryo-ct-prior-v2-block.py')
PRIOR_MAP_V2 = json.loads((ROOT / 'registry/cryo-ct-prior-map-v2.json').read_text())
PROTOCOL_V2 = json.loads((ROOT / 'registry/machine-acceptance-protocol-v2.json').read_text())


def t_v2_map_and_spec_agree():
    assert tuple(c['name'] for c in PRIOR_MAP_V2['channels']) == B.PRIOR_V2_CHANNELS == P2.CHANNELS
    assert B.PRIOR_V2_SPEC['channels'] == ['rgb_to_0_1'] * 3 + ['nonorm'] * 4
    assert B.PRIOR_V2_SPEC['dataset_id'] == 503 and B.PRIOR_V2_SPEC['dataset_id'] != B.VARIANTS['rgb-plus-ct-prior']['dataset_id']
    assert B.variant_spec('rgb-plus-ct-prior', 2) is B.PRIOR_V2_SPEC and B.variant_spec('rgb-plus-ct-prior', 1) is B.VARIANTS['rgb-plus-ct-prior']
    assert B.report_stem('rgb-plus-ct-prior', 2) == 'cryo-nnunet-dataset-block2-rgb-plus-ct-prior-v2'
    assert B.report_stem('rgb-plus-ct-prior', 1) == 'cryo-nnunet-dataset-block2-rgb-plus-ct-prior', 'the version 1 report name changed'
    assert PRIOR_MAP_V2['distance_max_mm'] == P2.DIST_MAX_MM == 15.0
    assert PRIOR_MAP_V2['version'] == 2 and PRIOR_MAP_V2['supersedes'].startswith('registry/cryo-ct-prior-map.json')
    assert P2.MAP_V1.exists(), 'the version 1 prior map must stay on disk: the 502 run is bound to it'


def t_v2_vote_is_strict_majority_of_eligible():
    shape = (2, 2, 1)
    a, b, c = (np.zeros(shape, bool) for _ in range(3))
    e = np.ones(shape, bool)
    a[0, 0] = b[0, 0] = True; a[1, 1] = True
    cons, dis, votes, n = P2.vote_bone([a, b, c], [e, e, e])
    assert cons[0, 0, 0] and dis[0, 0, 0] and not cons[1, 1, 0] and dis[1, 1, 0]
    none = np.zeros(shape, bool)
    cons, dis, votes, n = P2.vote_bone([a, b, c], [e, e, none])       # two eligible: 1 of 2 is not a majority
    assert cons[0, 0, 0] and not dis[0, 0, 0] and not cons[1, 1, 0] and dis[1, 1, 0]
    cons, dis, votes, n = P2.vote_bone([a, b, c], [none, none, none])  # nobody eligible: an ineligible vote is discarded
    assert not cons.any() and not dis.any() and votes.max() == 0 and n.max() == 0
    cls, conflicts = P2.class_volume(a, b)                              # bone wins the conflict once
    assert cls[0, 0, 0] == 1 and conflicts == 1 and cls[1, 1, 0] == 1


def t_v2_distance_encoding():
    sl = np.zeros((9, 9), bool); sl[4, 4] = True
    d = P2.distance_channel(sl, (0.666, 0.666))
    assert d.dtype == np.uint8 and d[4, 4] == 0
    assert d[4, 7] == round(255 * 3 * 0.666 / 15) == 34 and d[1, 4] == 34, 'the in-plane distance is not in mm'
    assert (P2.distance_channel(np.zeros((3, 3), bool), (0.666, 0.666)) == 255).all(), 'a section without bone must be 255, never 0'
    far = np.zeros((80, 80), bool); far[0, 0] = True
    assert P2.distance_channel(far, (0.666, 0.666))[79, 79] == 255, 'the clip at 15 mm failed'
    # the dataset builder scales the channel to 0..1 float32, the same range as the colour channels
    assert B.PRIOR_V2_DISTANCE_SCALE == 255.0


def t_v2_report_matches_disk():
    rp = ROOT / 'generated/cryo-ct-prior-v2-block2.json'
    assert rp.exists(), 'the version 2 prior report is missing: run build-cryo-ct-prior-v2-block.py'
    rep = json.loads(rp.read_text())
    assert rep['prior_version'] == 2
    assert rep['inputs']['prior_map_v2_sha256'] == P2.sha256_file(ROOT / 'registry/cryo-ct-prior-map-v2.json'), 'report written against another map'
    assert rep['inputs']['prior_map_v1_sha256'] == P2.sha256_file(ROOT / 'registry/cryo-ct-prior-map.json'), 'the version 1 map changed'
    assert [c['name'] for c in rep['channels']] == list(P2.CHANNELS)
    block = ROOT / 'data/derived/nlm-vhf/cryosections/block2'
    for c in P2.CHANNELS:
        p = block / f'ct-prior-v2-{c}.nii.gz'
        if not p.exists():
            continue
        assert rep['outputs'][c]['sha256'] == P2.sha256_file(p), f'{p.name} changed after the report'
        vol = np.asanyarray(nib.load(p).dataobj)
        if c == 'bone-distance':
            bone = np.asanyarray(nib.load(block / 'ct-prior-v2-bone.nii.gz').dataobj) > 0
            assert (vol[bone] == 0).all(), 'distance inside consensus bone is not 0'
            empty = ~bone.any(axis=(0, 1))
            if empty.any():
                assert (vol[:, :, empty] == 255).all(), 'a section without consensus bone is not 255'
        else:
            assert set(np.unique(vol).tolist()) <= {0, 1}, f'{c} is not binary'
    cov = rep['coverage']['primary_training_slices']
    assert cov['slices'] == 197
    assert 0.0 <= cov['bone']['prior_recall_of_reference'] <= 1.0
    hist = rep['ct_grid']['eligible_votes_histogram']
    assert not any(k.startswith('eligible_0_votes_') and not k.endswith('_votes_0') for k in hist), 'a vote was counted where nobody was eligible'


def t_v2_prior_never_the_target():
    fixed = PROTOCOL_V2['identity_by_hash']['fixed_now']
    assert 'cryo-ct-prior-map' not in json.dumps(fixed), 'a prior map entered the frozen protocol v2 identity'
    assert fixed['tissue_map_sha256'] == P.sha256_file(ROOT / 'registry/cryo-tissue-map.json'), 'registry/cryo-tissue-map.json changed: protocol v2 is no longer valid'
    assert fixed['tissue_classes_volume_sha256'] == P.sha256_file(ROOT / 'data/derived/nlm-vhf/cryosections/block2/tissue-classes.nii.gz'), 'the reference volume changed'


def t_v2_builder_output_from_a_real_run():
    """Run the builder with --prior-version 2 into a temp tree: 7 channels, the four prior channels equal the volumes on
    disk (distance as float32 / 255), colour and target identical to the version 1 build."""
    block = ROOT / 'data/derived/nlm-vhf/cryosections/block2'
    for c in P2.CHANNELS:
        if not (block / f'ct-prior-v2-{c}.nii.gz').exists():
            raise AssertionError(f'ct-prior-v2-{c}.nii.gz is not on disk: the version 2 builder cannot be exercised')
    man = json.loads((block / 'manifest.json').read_text())
    nk, nj, ni = man['grid']['shape_kji3'][:3]
    with tempfile.TemporaryDirectory() as d:
        cmd = [sys.executable, str(ROOT / 'scripts/build-cryo-nnunet-dataset.py'), '--block', str(block),
               '--variant', 'rgb-plus-ct-prior', '--prior-version', '2', '--slices', 'train', '--out', d]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f'the builder failed: {r.stderr[-400:]}'
        root = Path(d) / B.PRIOR_V2_SPEC['name']
        dj = json.loads((root / 'dataset.json').read_text())
        assert len(dj['channel_names']) == 7 and dj['channel_names']['6'] == 'nonorm' and dj['labels']['ignore'] == B.NNUNET_IGNORE
        rep = json.loads((Path(d) / 'cryo-nnunet-dataset-block2-rgb-plus-ct-prior-v2.json').read_text())
        assert rep['prior_version'] == 2 and rep['dataset_id'] == 503 and len(rep['channel_meaning']) == 7
        assert rep['inputs']['protocol_version'] == 2, 'a version 2 dataset must name protocol version 2'
        assert set(rep['inputs']['ct_prior_v2']) == set(P2.CHANNELS)
        assert not (Path(d) / 'cryo-nnunet-dataset-block2-rgb-plus-ct-prior.json').exists(), 'the version 1 report name was used'
        rgb = np.load(block / 'rgb-kji.npy', mmap_mode='r')
        tissue = np.asanyarray(nib.load(block / 'tissue-classes.nii.gz').dataobj)
        vols = {c: np.asanyarray(nib.load(block / f'ct-prior-v2-{c}.nii.gz').dataobj) for c in P2.CHANNELS}
        k_first = man['block']['k_first']
        cases = sorted((root / 'labelsTr').glob('*.nii.gz'))
        assert len(cases) == 197
        for lf in cases[:2] + cases[len(cases) // 2:len(cases) // 2 + 2] + cases[-2:]:
            case = lf.name[:-len('.nii.gz')]
            z = int(case.split('_k')[1]) - k_first
            lab = np.squeeze(np.asanyarray(nib.load(lf).dataobj))
            want = tissue[:, :, z].copy(); want[want == 255] = B.NNUNET_IGNORE
            assert lab.shape == (ni, nj) and np.array_equal(lab, want), f'{case}: target differs from the tissue classes'
            for c in range(3):
                got = np.squeeze(np.asanyarray(nib.load(root / 'imagesTr' / f'{case}_{c:04d}.nii.gz').dataobj))
                assert np.array_equal(got, rgb[z][:, :, c].T), f'{case}: colour channel {c} wrong'
            for c, name in enumerate(P2.CHANNELS, start=3):
                img = nib.load(root / 'imagesTr' / f'{case}_{c:04d}.nii.gz')
                got = np.squeeze(np.asanyarray(img.dataobj))
                if name == 'bone-distance':
                    assert img.get_data_dtype() == np.float32, f'{case}: the distance channel is not float32'
                    assert np.allclose(got, vols[name][:, :, z].astype(np.float32) / 255.0, atol=1e-7), f'{case}: distance channel wrong'
                    assert got.min() >= 0.0 and got.max() <= 1.0
                else:
                    assert img.get_data_dtype() == np.uint8 and np.array_equal(got, vols[name][:, :, z]), f'{case}: prior channel {name} wrong'


def t_v2_refuses_rgb_only():
    B.variant_spec('rgb-only', 2)


for n, f in [('v2 map, builder and spec agree', t_v2_map_and_spec_agree),
             ('v2 vote is a strict majority of the eligible models', t_v2_vote_is_strict_majority_of_eligible),
             ('v2 distance encoding', t_v2_distance_encoding),
             ('v2 prior report matches disk', t_v2_report_matches_disk),
             ('v2 prior is not the target and protocol v2 identity is untouched', t_v2_prior_never_the_target),
             ('v2 builder output from a real run', t_v2_builder_output_from_a_real_run)]:
    check(n, f)
refuses('prior version 2 for rgb-only', t_v2_refuses_rgb_only)

print(json.dumps({'ok': not failures, 'failures': failures}))
sys.exit(1 if failures else 0)
