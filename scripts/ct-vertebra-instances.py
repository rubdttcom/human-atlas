"""Vertebra consensus by geometric instance, without imposing names or counts (plan B, stage 1).

Usage: python scripts/ct-vertebra-instances.py nlm | denver [vertebrae | ribs_left | ribs_right] [--selftest]

The same machinery runs on the rib families (`ribs_left`, `ribs_right`: TotalSegmentator `rib_<side>_1..12`,
MOOSE `clin_ct_ribs` `rib_<side>_1..13`, Skellytour `<SIDE>_RIB_1..12`), with ids RL01.. / RR01.. from cranial
to caudal, coronal projection panels and no HRA chain (the HRA female skeleton has no rib meshes). Outputs
then go to generated/ct-rib-instances-<ct>-<side>.json and rib-<side>-*.nii.gz.

Why. On this donor three CT models (TotalSegmentator `total`, MOOSE `clin_ct_vertebrae`, Skellytour
`high`) find six lumbar-type vertebral bodies and force their own names onto them differently, so a vote
by name is meaningless in the lumbar spine. This script votes on *instances*:

1. Candidates. For every model and every vertebral label (C1..L5 plus TotalSegmentator `S1`, MOOSE `L6`,
   both models' `sacrum`, Skellytour `VERT_1..24`), the connected components (26-connectivity) with volume
   >= MIN_ML are candidates; smaller components are fragments and are only counted. A component is a
   candidate, not a proof of one vertebra: MOOSE fragments bodies, Skellytour puts one name on two bodies.
2. Correspondence between models by voxel overlap (IoU, mutual coverage) and by craniocaudal order, with
   explicit states: matched, split (one candidate covers several of the other model), merge (the other
   model covers several of ours), partial, unmatched. Centroid distances are reported in mm.
3. Instances. Candidates are grouped by overlap (IoU >= 0.2). A group with at most one candidate per
   model is one instance. A group where some model has several candidates is partitioned by the model
   with the most candidates in it (finest partition); the other models' candidates are assigned to the
   partition instance that covers them, or, when one candidate spans several instances (a merge), their
   voxels go to the nearest partition seed and the model's identity vote for those instances is recorded
   as `merge`, never as a confirmation of the split. Instances get neutral ids V01.. from cranial to
   caudal; the sacrum candidates form an instance with role `sacrum`. No id carries an anatomical name.
4. Vote per voxel. One vote per model per instance. A model is eligible on a voxel when it processed
   that region (Skellytour ran on a body-cropped grid: outside the crop it is *unprocessed*, not
   negative) and supports the class (Skellytour has no sacrum class: *unsupported* there). A model that
   is eligible and has no candidate on an instance is a *negative* prediction, counted as a vote against.
   Consensus = strict majority of the eligible votes; everything with at least one vote is kept in the
   review map. Per instance: consensus volume, union volume, unanimity fraction, votes and eligible
   models, per-model state and IoU against the consensus.
5. External same-donor reference (evidence for naming, not a decision). The HRA united-female v1.5
   skeleton was modelled on the Visible Human Female and carries 7 + 12 + 6 = 25 vertebrae and a fused
   sacrum (NIH 3D entry 3DPX-020988 states "The Visible Human Female has 6 lumbar vertebrae"). The HRA
   vertebra chain is carried into the VHF frame by `transforms/hra-stage-to-vhf.json` and matched to the
   instance chain by order from the sacrum upwards; the HRA name per instance is reported as
   `hra_name_by_order` with the z offset in mm. It is written as evidence with provenance; every
   instance keeps `name_status: pending`.

Outputs
  generated/ct-vertebra-instances-<ct>.json               table, correspondence, votes, HRA evidence
  generated/ct-vertebra-instances-<ct>/{sagittal,models,coronal,axial}.png   review panels
  data/derived/<ct dir>/consensus/vertebra-instances.nii.gz   consensus instance id per voxel (uint8)
  data/derived/<ct dir>/consensus/vertebra-review.nii.gz      any-vote instance id (candidates kept for review)
  data/derived/<ct dir>/consensus/vertebra-votes.nii.gz       votes for the winning instance per voxel
  data/derived/<ct dir>/consensus/vertebra-eligible.nii.gz    eligible models per voxel
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.orientations import apply_orientation, axcodes2ornt, io_orientation, ornt_transform
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
OPTS = {a.split('=')[0]: (a.split('=', 1)[1] if '=' in a else True) for a in sys.argv[1:] if a.startswith('--')}
INPUTS = Path(OPTS['--inputs']) if '--inputs' in OPTS else None     # test harness: directory with ts.nii.gz, moose.nii.gz, moose_indices.json, hu.nii.gz, skellytour/{plan.json,skellytour_high.json,skellytour_high.nii.gz}
OUT_DIR = Path(OPTS['--out']) if '--out' in OPTS else None
NO_PANELS = '--no-panels' in OPTS
NO_HRA = '--no-hra' in OPTS or INPUTS is not None
ALLOW_INCOMPLETE = '--allow-incomplete' in OPTS
CT = ARGS[0] if ARGS else 'nlm'
FAMILY = ARGS[1] if len(ARGS) > 1 else 'vertebrae'
if FAMILY not in ('vertebrae', 'ribs_left', 'ribs_right'):
    sys.exit('family must be vertebrae, ribs_left or ribs_right')
SIDE = FAMILY.split('_')[1] if FAMILY != 'vertebrae' else None
MEMBER_ROLE = 'vertebra' if FAMILY == 'vertebrae' else 'rib'
ID_PREFIX = 'V' if FAMILY == 'vertebrae' else ('RL' if SIDE == 'left' else 'RR')
MOOSE_TASK = 'vertebrae' if FAMILY == 'vertebrae' else 'ribs'
SELFTEST = '--selftest' in sys.argv
MIN_ML = 3.0          # smaller components are fragments, not candidates
IOU_GROUP = 0.20      # overlap that links two candidates of different models into one group
IOU_MATCH = 0.50      # one-to-one match
COVER_PART = 0.20     # a candidate covering >= 20 % of two partners is a split/merge
MODEL_ORDER = ['totalseg', 'skellytour', 'moose']   # tie-break for the partition model
OVERSIZE = 1.4        # a candidate > 1.4 x the mean of its two neighbours (same model) is treated as a merge of bodies

if INPUTS is not None:
    TS = INPUTS / 'ts.nii.gz'
    MOOSE = INPUTS / 'moose.nii.gz'
    MOOSE_IDX = INPUTS / 'moose_indices.json'
    SKELLY_DIR = INPUTS / 'skellytour'
    HU = INPUTS / 'hu.nii.gz'
    OUT_NII = (OUT_DIR or INPUTS / 'out') / 'nii'
    RAS_TO_VHF = np.eye(4)
    VOX_TO_VHF = None
elif CT == 'nlm':
    TS = ROOT / 'data/derived/nlm-vhf/totalseg.nii'
    MOOSE = ROOT / f'data/derived/nlm-vhf/moose/segmentations/clin_CT_{MOOSE_TASK}_segmentation_CT_vhf.nii.gz'
    MOOSE_IDX = ROOT / f'data/derived/nlm-vhf/moose/segmentations/clin_CT_{MOOSE_TASK}_organ_indices.json'
    SKELLY_DIR = ROOT / 'data/derived/nlm-vhf/skellytour'
    HU = ROOT / 'data/derived/nlm-vhf/vhf-fresh-ct.nii.gz'
    OUT_NII = ROOT / 'data/derived/nlm-vhf/consensus'
    RAS_TO_VHF = np.array(json.loads((ROOT / 'transforms/nlm-ct-to-vhf.json').read_text())['matrix_row_major']).reshape(4, 4)
    VOX_TO_VHF = None
elif CT == 'denver':
    TS = ROOT / 'data/derived/denver/priors/totalseg/total.nii.gz'
    seg = next((ROOT / 'data/derived/denver/priors/moose').glob('*/segmentations'))
    MOOSE = seg / f'clin_CT_{MOOSE_TASK}_segmentation_CT_denverct.nii.gz'
    MOOSE_IDX = seg / f'clin_CT_{MOOSE_TASK}_organ_indices.json'
    SKELLY_DIR = ROOT / 'data/derived/denver/priors/skellytour'
    HU = ROOT / 'data/derived/denver/aligned-ct-nii/denver_aligned_ct_hu.nii.gz'
    OUT_NII = ROOT / 'data/derived/denver/priors/consensus'
    RAS_TO_VHF = None
    VOX_TO_VHF = np.array(json.loads((ROOT / 'transforms/denver-aligned-ct-voxel-to-vhf.json').read_text())['matrix_row_major']).reshape(4, 4)
else:
    sys.exit('usage: ct-vertebra-instances.py nlm|denver [--selftest]')
if OUT_DIR is not None or INPUTS is not None:
    base = OUT_DIR or INPUTS / 'out'
    OUT_JSON = base / f'{FAMILY}.json'
    OUT_PNG = base / f'{FAMILY}-panels'
    NII_STEM = FAMILY
    OUT_NII = base / 'nii'
elif FAMILY == 'vertebrae':
    OUT_JSON = ROOT / f'generated/ct-vertebra-instances-{CT}.json'
    OUT_PNG = ROOT / f'generated/ct-vertebra-instances-{CT}'
    NII_STEM = 'vertebra'
elif FAMILY != 'vertebrae':
    OUT_JSON = ROOT / f'generated/ct-rib-instances-{CT}-{SIDE}.json'
    OUT_PNG = ROOT / f'generated/ct-rib-instances-{CT}-{SIDE}'
    NII_STEM = f'rib-{SIDE}'

VERT24 = [f'C{i}' for i in range(1, 8)] + [f'T{i}' for i in range(1, 13)] + [f'L{i}' for i in range(1, 6)]
TS_CLASS = {v: int(k) for k, v in json.loads((ROOT / 'data/derived/nlm-vhf/totalseg-classmap.json').read_text())['total'].items()}
MO_ALL = {v['name']: int(k) for k, v in json.loads(MOOSE_IDX.read_text())['organ_indices'].items()}
if FAMILY == 'vertebrae':
    TS_LABELS = {f'vertebrae_{v}': TS_CLASS[f'vertebrae_{v}'] for v in VERT24 + ['S1']}
    TS_LABELS['sacrum'] = TS_CLASS['sacrum']
    MO_LABELS = {n: i for n, i in MO_ALL.items() if n.startswith('vertebra_') or n == 'sacrum'}
    SK_LABELS = {f'VERT_{i}': 35 + i for i in range(1, 25)}
else:
    TS_LABELS = {f'rib_{SIDE}_{i}': TS_CLASS[f'rib_{SIDE}_{i}'] for i in range(1, 13)}
    MO_LABELS = {n: i for n, i in MO_ALL.items() if n.startswith(f'rib_{SIDE}_')}
    SK_LABELS = {f'{SIDE.upper()}_RIB_{i}': (11 if SIDE == 'left' else 23) + i for i in range(1, 13)}
SK_PELVIS = 2
ROLE = lambda label: 'sacrum' if label == 'sacrum' else MEMBER_ROLE   # noqa: E731


def rel(path):
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def load(path):
    im = nib.load(path)
    a = np.asanyarray(im.dataobj)
    return im, (a.astype(np.uint8) if a.max() < 256 else a.astype(np.int16))


print('loading', CT, flush=True)
ts_im, ts_full = load(TS)
affine = ts_im.affine
mo_im, mo_full = load(MOOSE)
sk_im, sk_full = load(SKELLY_DIR / 'skellytour_high.nii.gz')
for name, im in [('moose', mo_im), ('skellytour', sk_im)]:
    if im.shape != ts_im.shape or not np.allclose(im.affine, affine, atol=1e-3):
        sys.exit(f'{name} grid differs from TotalSegmentator: shape {im.shape} vs {ts_im.shape}, affine max diff {np.abs(im.affine - affine).max():.4f}')
plan = json.loads((SKELLY_DIR / 'plan.json').read_text())
i0, i1, j0, j1 = plan['crop']
seams = [p['core0'] for p in plan['chunks'][1:]]
vox_ml = float(abs(np.linalg.det(affine[:3, :3])) / 1000)
SPACING = np.linalg.norm(affine[:3, :3], axis=0)   # mm per voxel along each array axis (orthogonal grids)
# Skellytour processed region: the crop of plan.json in-plane, and along z only the chunk cores that the merge manifest
# reports as done. An incomplete manifest (missing chunks) is refused unless --allow-incomplete: a missing block must
# never count as a negative prediction.
manifest_path = SKELLY_DIR / 'skellytour_high.json'
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
if 'complete' in manifest:
    if manifest.get('chunks_planned') != len(plan['chunks']):
        sys.exit(f'Skellytour manifest plans {manifest.get("chunks_planned")} chunks, plan.json has {len(plan["chunks"])}')
    if not manifest['complete'] and not ALLOW_INCOMPLETE:
        sys.exit(f'Skellytour manifest incomplete (missing chunks {manifest.get("missing")}); rerun the merge or pass --allow-incomplete')
    done_cores = [(c['core0'], c['core1']) for c in manifest['chunks']]
    skelly_manifest_info = {'format': 'manifest', 'complete': manifest['complete'], 'missing_chunks': manifest.get('missing', []), 'merged_sha256': manifest.get('merged_sha256')}
else:
    done_cores = [(p['core0'], p['core1']) for p in plan['chunks']]
    skelly_manifest_info = {'format': 'legacy (plan.json only; completeness not verifiable)', 'complete': None, 'missing_chunks': None, 'merged_sha256': None}
if 'crop_ijk' in manifest and (manifest['crop_ijk']['i'] != [i0, i1] or manifest['crop_ijk']['j'] != [j0, j1]):
    sys.exit('Skellytour manifest crop differs from plan.json')

# region of interest: union bounding box of every vertebral label of every model, padded
def label_box(arr, ids):
    objs = ndimage.find_objects(arr)
    boxes = [objs[i - 1] for i in ids if i - 1 < len(objs) and objs[i - 1] is not None]
    return boxes


boxes = label_box(ts_full, TS_LABELS.values()) + label_box(mo_full, MO_LABELS.values()) + label_box(sk_full, SK_LABELS.values())
PAD = 8
roi = tuple(slice(max(0, min(b[d].start for b in boxes) - PAD), min(ts_full.shape[d], max(b[d].stop for b in boxes) + PAD)) for d in range(3))
off = np.array([s.start for s in roi])
print('roi', [(s.start, s.stop) for s in roi], 'voxels', int(np.prod([s.stop - s.start for s in roi])), flush=True)
ts, mo, sk = ts_full[roi], mo_full[roi], sk_full[roi]
del ts_full, mo_full
processed = {'totalseg': np.ones(ts.shape, bool), 'moose': np.ones(ts.shape, bool), 'skellytour': np.zeros(ts.shape, bool)}
for z0, z1 in done_cores:
    processed['skellytour'][max(0, i0 - off[0]):max(0, i1 - off[0]), max(0, j0 - off[1]):max(0, j1 - off[1]), max(0, z0 - off[2]):max(0, z1 - off[2])] = True
supports_sacrum = {'totalseg': True, 'moose': True, 'skellytour': False}
arrays = {'totalseg': (ts, TS_LABELS), 'moose': (mo, MO_LABELS), 'skellytour': (sk, SK_LABELS)}


def to_ras(vox_roi):
    return (affine @ np.r_[np.asarray(vox_roi) + off, 1])[:3]


def to_vhf(vox_roi):
    v = np.asarray(vox_roi) + off
    if VOX_TO_VHF is not None:
        return (VOX_TO_VHF @ np.r_[v, 1])[:3]
    return (RAS_TO_VHF @ np.r_[(affine @ np.r_[v, 1])[:3], 1])[:3]


# 1. candidates ---------------------------------------------------------------------------------------
STRUCT = np.ones((3, 3, 3), bool)
cands = []            # dicts
cand_map = {}         # model -> int16 roi array of candidate ids (index into cands + 1)
fragments = {}
for m, (arr, labels) in arrays.items():
    cm = np.zeros(arr.shape, np.int16)
    fragments[m] = {}
    for label, lid in labels.items():
        mask = arr == lid
        if not mask.any():
            continue
        lab, n = ndimage.label(mask, structure=STRUCT)
        sizes = np.bincount(lab.ravel())[1:]
        small = [(k + 1, int(s)) for k, s in enumerate(sizes) if s * vox_ml < MIN_ML]
        if small:
            fragments[m][label] = {'count': len(small), 'volume_ml': round(sum(s for _, s in small) * vox_ml, 2)}
        for k, s in enumerate(sizes):
            if s * vox_ml < MIN_ML:
                continue
            comp = lab == k + 1
            c = np.array(ndimage.center_of_mass(comp))
            box = ndimage.find_objects(comp.astype(np.uint8))[0]
            cid = len(cands) + 1
            cm[comp] = cid
            cands.append({'cid': cid, 'model': m, 'label': label, 'role': ROLE(label), 'component': k + 1, 'components_of_label': int(n), 'voxels': int(s),
                          'volume_ml': round(float(s) * vox_ml, 2), 'centroid_vox': (c + off).round(1).tolist(), 'centroid_ras_mm': to_ras(c).round(1).tolist(),
                          'centroid_vhf_mm': to_vhf(c).round(1).tolist(), 'z_ras_mm': round(float(to_ras(c)[2]), 1),
                          'z_vox': [int(box[2].start + off[2]), int(box[2].stop + off[2])], 'box': [[int(b.start), int(b.stop)] for b in box]})
    cand_map[m] = cm
    print(m, 'candidates', sum(1 for c in cands if c['model'] == m), 'fragments', {k: v['count'] for k, v in fragments[m].items()}, flush=True)
by_id = {c['cid']: c for c in cands}


# 2. pairwise correspondence --------------------------------------------------------------------------
def intersections(ma, mb):
    both = (ma > 0) & (mb > 0)
    if not both.any():
        return {}
    pairs, cnt = np.unique(np.stack([ma[both], mb[both]]).astype(np.int64), axis=1, return_counts=True)
    return {(int(a), int(b)): int(k) for (a, b), k in zip(pairs.T, cnt)}


def correspondence(map_a, map_b, cands_a, cands_b):
    """States of every candidate of A against model B (and the reverse), from voxel overlap and craniocaudal order."""
    inter = intersections(map_a, map_b)
    vol = {c['cid']: c['voxels'] for c in cands_a + cands_b}
    partners_a = defaultdict(dict)   # a -> {b: inter}
    partners_b = defaultdict(dict)
    for (a, b), k in inter.items():
        partners_a[a][b] = k
        partners_b[b][a] = k

    def state(x, partners_x, partners_other, others):
        """x is a candidate of one model; partners_x its overlaps in the other model."""
        px = partners_x.get(x['cid'], {})
        rows = []
        for y, k in sorted(px.items(), key=lambda kv: -kv[1]):
            if k / vol[x['cid']] < 0.05 and k / vol[y] < 0.05:
                continue   # touching boundaries are not a correspondence
            iou = k / (vol[x['cid']] + vol[y] - k)
            rows.append({'cid': y, 'label': by_id[y]['label'], 'iou': round(iou, 3), 'covers_me': round(k / vol[x['cid']], 3), 'i_cover_it': round(k / vol[y], 3),
                         'intersection_ml': round(k * vox_ml, 2), 'centroid_distance_mm': round(float(np.linalg.norm(np.array(by_id[y]['centroid_ras_mm']) - np.array(x['centroid_ras_mm']))), 1)})
        if not rows:
            return 'unmatched', rows
        best = rows[0]
        # does the best partner also cover another candidate of my model substantially? then it merges us
        others_in_best = [a for a, k in partners_other.get(best['cid'], {}).items() if a != x['cid'] and k / vol[a] >= COVER_PART]
        many = [r for r in rows if r['i_cover_it'] >= COVER_PART]
        if best['iou'] >= IOU_MATCH and not others_in_best and len(many) <= 1:
            return 'matched', rows
        if len(many) >= 2:
            return 'split', rows          # I cover several partners: I am the merged one (my label spans several bodies of theirs)
        if others_in_best:
            return 'merge', rows          # their partner spans me and another of mine: their label merges our bodies
        return 'partial', rows

    out = {'a_to_b': {}, 'b_to_a': {}}
    for x in cands_a:
        s, rows = state(x, partners_a, partners_b, cands_b)
        out['a_to_b'][f"{x['label']}#{x['component']}"] = {'cid': x['cid'], 'state': s, 'volume_ml': x['volume_ml'], 'z_ras_mm': x['z_ras_mm'], 'partners': rows}
    for x in cands_b:
        s, rows = state(x, partners_b, partners_a, cands_a)
        out['b_to_a'][f"{x['label']}#{x['component']}"] = {'cid': x['cid'], 'state': s, 'volume_ml': x['volume_ml'], 'z_ras_mm': x['z_ras_mm'], 'partners': rows}
    # craniocaudal order of matched pairs must be monotonic
    matched = [(r['z_ras_mm'], by_id[r['partners'][0]['cid']]['z_ras_mm']) for r in out['a_to_b'].values() if r['state'] == 'matched']
    matched.sort()
    zb = [b for _, b in matched]
    out['order'] = {'matched_pairs': len(matched), 'order_violations': int(sum(1 for i in range(len(zb) - 1) if zb[i] >= zb[i + 1]))}
    out['state_counts'] = {'a_to_b': dict(sorted(((s, sum(1 for r in out['a_to_b'].values() if r['state'] == s)) for s in {r['state'] for r in out['a_to_b'].values()}))),
                           'b_to_a': dict(sorted(((s, sum(1 for r in out['b_to_a'].values() if r['state'] == s)) for s in {r['state'] for r in out['b_to_a'].values()})))}
    return out


pairwise = {}
models = list(arrays)
for i in range(len(models)):
    for j in range(i + 1, len(models)):
        a, b = models[i], models[j]
        pairwise[f'{a}|{b}'] = correspondence(cand_map[a], cand_map[b], [c for c in cands if c['model'] == a], [c for c in cands if c['model'] == b])
        print('correspondence', a, b, pairwise[f'{a}|{b}']['state_counts'], 'order violations', pairwise[f'{a}|{b}']['order']['order_violations'], flush=True)


# 3. instances ----------------------------------------------------------------------------------------
# overlap graph
adj = defaultdict(set)
all_inter = {}
for i in range(len(models)):
    for j in range(i + 1, len(models)):
        for (a, b), k in intersections(cand_map[models[i]], cand_map[models[j]]).items():
            iou = k / (by_id[a]['voxels'] + by_id[b]['voxels'] - k)
            all_inter[(a, b)] = all_inter[(b, a)] = k
            if iou >= IOU_GROUP:
                adj[a].add(b)
                adj[b].add(a)
groups, seen = [], set()
for c in cands:
    if c['cid'] in seen:
        continue
    stack, g = [c['cid']], set()
    while stack:
        x = stack.pop()
        if x in g:
            continue
        g.add(x)
        stack.extend(adj[x] - g)
    seen |= g
    groups.append(sorted(g))

instances = []        # dicts, later sorted cranial -> caudal
inst_map = {m: np.zeros(ts.shape, np.uint8) for m in models}   # per model, instance id per voxel (filled after ids are final)
assign = {}           # cid -> (instance index, state)
for g in groups:
    per_model = defaultdict(list)
    for cid in g:
        per_model[by_id[cid]['model']].append(cid)
    if max(len(v) for v in per_model.values()) == 1:
        inst = {'members': {by_id[cid]['model']: cid for cid in g}, 'seed_cids': list(g), 'partition_model': None, 'group_kind': 'clean' if len(g) > 1 else 'single'}
        for cid in g:
            assign[cid] = (len(instances), 'matched' if len(g) > 1 else 'single')
        instances.append(inst)
        continue
    # conflict: partition by the model with the most candidates (tie -> MODEL_ORDER)
    pm = sorted(per_model, key=lambda m: (-len(per_model[m]), MODEL_ORDER.index(m)))[0]
    seeds = sorted(per_model[pm], key=lambda s: -by_id[s]['z_ras_mm'])

    def covering(m, seed):
        """Candidate of model m that covers >= 50 % of the seed, else None."""
        best, bf = None, 0.0
        for cid in per_model[m]:
            f = all_inter.get((seed, cid), 0) / by_id[seed]['voxels']
            if f > bf:
                best, bf = cid, f
        return best if bf >= 0.5 else None

    def oversized(cid):
        """A candidate much larger than its own model's neighbours along the spine is a merge of bodies, not one body."""
        own = [c for c in cands if c['model'] == by_id[cid]['model'] and c['role'] == MEMBER_ROLE]
        med = float(np.median([c['volume_ml'] for c in own]))
        chain = sorted((c for c in own if c['volume_ml'] >= 0.4 * med or c['cid'] == cid), key=lambda c: -c['z_ras_mm'])   # fragments are not neighbours
        k = next(i for i, c in enumerate(chain) if c['cid'] == cid)
        neigh = [chain[i]['volume_ml'] for i in (k - 1, k + 1) if 0 <= i < len(chain)]
        return bool(neigh) and by_id[cid]['volume_ml'] > OVERSIZE * float(np.mean(neigh))   # mean, not min: ribs 11 and 12 shrink fast

    # a component of the partition model is a candidate, not a proof of one body: two consecutive seeds are one
    # instance when no other model separates them and at least one other model covers both with ONE candidate of
    # normal size (an oversized covering candidate is itself a merge of two bodies and does not argue for merging)
    seed_sets = [[s] for s in seeds]
    changed = True
    while changed:
        changed = False
        for i in range(len(seed_sets) - 1):
            A, B = seed_sets[i], seed_sets[i + 1]
            joint, sep = False, False
            for m in per_model:
                if m == pm:
                    continue
                ca = {covering(m, x) for x in A} - {None}
                cb = {covering(m, x) for x in B} - {None}
                if ca and cb:
                    if ca == cb and len(ca) == 1:
                        if not oversized(next(iter(ca))):
                            joint = True
                    else:
                        sep = True
            if joint and not sep:
                seed_sets[i:i + 2] = [A + B]
                changed = True
                break
    first = len(instances)
    for ss in seed_sets:
        main = max(ss, key=lambda x: by_id[x]['voxels'])
        instances.append({'members': {pm: main}, 'seed_cids': list(ss), 'partition_model': pm, 'group_kind': 'partitioned', 'group_cids': g,
                          'seed_merged_from': [f"{by_id[x]['label']}#{by_id[x]['component']}" for x in ss] if len(ss) > 1 else None})
        for x in ss:
            assign[x] = (len(instances) - 1, 'seed')
    for m, cids in per_model.items():
        if m == pm:
            continue
        for cid in cids:
            cover = {i: sum(all_inter.get((cid, x), 0) for x in ss) / by_id[cid]['voxels'] for i, ss in enumerate(seed_sets)}
            spans = [i for i, f in cover.items() if f >= COVER_PART]
            best = max(cover, key=cover.get)
            if len(spans) >= 2:
                for i in spans:   # identity vote is a merge on every spanned instance; voxels split by nearest seed below
                    instances[first + i]['members'].setdefault(m, cid)
                assign[cid] = ([first + i for i in spans], 'merge')
            elif cover[best] > 0:
                k = first + best
                if m in instances[k]['members']:   # a second candidate of the same model on one seed: keep the larger as member, record the other as extra
                    other = instances[k]['members'][m]
                    if by_id[cid]['voxels'] > by_id[other]['voxels']:
                        instances[k]['members'][m] = cid
                        instances[k].setdefault('extra_cids', []).append(other)
                        assign[other] = (k, 'extra')
                    else:
                        instances[k].setdefault('extra_cids', []).append(cid)
                        assign[cid] = (k, 'extra')
                        continue
                instances[k]['members'][m] = cid
                assign[cid] = (k, 'matched' if cover[best] >= 0.5 else 'partial')
            else:
                instances.append({'members': {m: cid}, 'seed_cids': [cid], 'partition_model': None, 'group_kind': 'single'})
                assign[cid] = (len(instances) - 1, 'single')

# order cranial -> caudal by the z (RAS) of the seed centroid; ids V01.. ; sacrum role from the members' labels
for inst in instances:
    zs = [by_id[c]['z_ras_mm'] for c in inst['seed_cids']]
    inst['z_ras_mm'] = round(float(np.mean(zs)), 1)
    inst['role'] = 'sacrum' if any(by_id[c]['role'] == 'sacrum' for c in inst['members'].values()) else MEMBER_ROLE
order = sorted(range(len(instances)), key=lambda k: -instances[k]['z_ras_mm'])
new_index = {old: new for new, old in enumerate(order)}
instances = [instances[k] for k in order]
for k, inst in enumerate(instances):
    inst['id'] = f'{ID_PREFIX}{k + 1:02d}' if inst['role'] == MEMBER_ROLE else f'S{k + 1:02d}'
    inst['index'] = k + 1
for cid, (k, s) in list(assign.items()):
    assign[cid] = ([new_index[x] for x in k] if isinstance(k, list) else new_index[k], s)

# per-model instance maps
for cid, (k, s) in assign.items():
    c = by_id[cid]
    m = c['model']
    mask = cand_map[m] == cid
    if s == 'merge':
        # voxels of a merged candidate go to the nearest partition seed among the spanned instances (within the candidate's box)
        box = tuple(slice(b[0], b[1]) for b in c['box'])
        seed_map = np.zeros(ts.shape, np.uint8)
        for kk in k:
            inst = instances[kk]
            for sc in inst['seed_cids']:
                seed_map[cand_map[by_id[sc]['model']] == sc] = kk + 1
        sub = seed_map[box]
        if (sub > 0).any():
            idx = ndimage.distance_transform_edt(sub == 0, sampling=SPACING, return_indices=True)[1]
            nearest = sub[tuple(idx)]
            inst_map[m][box][mask[box]] = nearest[mask[box]]
    elif s != 'extra':
        inst_map[m][mask] = k + 1
    else:
        inst_map[m][mask] = k + 1   # extra candidate of the same model on the same instance: same instance vote (one model, one vote per voxel)

# 3b. detached pieces, geometric only (names never decide). A piece is an instance whose union volume is below
# PIECE_RATIO x the median union volume of the family and that at least one eligible model does not segment as its own
# object (a small object seen by every eligible model is a small bone). It is merged into the one instance whose union lies within
# FRAG_MM of it (surface distance in mm, anisotropic spacing honoured). With two instances in reach it merges only when
# the nearest is at least AMBIG_RATIO times closer than the next; otherwise it stays a separate `ambiguous` proposal,
# and with none in reach a separate `piece`. Label agreement with the target is recorded as evidence, never used.
PIECE_RATIO, FRAG_MM, AMBIG_RATIO = 0.5, 10.0, 2.0
n_inst = len(instances)
def union_mask(k):
    m = np.zeros(ts.shape, bool)
    for mm in models:
        m |= inst_map[mm] == k
    return m
union_vol = {k: int(union_mask(k).sum()) for k in range(1, n_inst + 1)}
member_vols = [v for k, v in union_vol.items() if instances[k - 1]['role'] == MEMBER_ROLE and v > 0]
med_vol = float(np.median(member_vols)) if member_vols else 0.0
pad_vox = np.ceil(FRAG_MM / SPACING).astype(int) + 1
merged_piece = {}
for k in range(1, n_inst + 1):
    inst = instances[k - 1]
    if inst['role'] != MEMBER_ROLE or union_vol[k] == 0 or union_vol[k] >= PIECE_RATIO * med_vol:
        inst['size_class'] = 'full' if union_vol[k] else 'empty'
        continue
    um = union_mask(k)
    # a small object that every eligible model segments as its own object is a small bone (rib 12, C3), not a piece
    n_eligible = sum(1 for m in models if float(processed[m][um].mean()) >= 0.5)
    if len(inst['members']) >= n_eligible:
        inst['size_class'] = 'full'
        inst['small_but_fully_supported'] = True
        continue
    obj = ndimage.find_objects(um.astype(np.uint8))[0]
    box = tuple(slice(max(0, o.start - pad_vox[d]), min(ts.shape[d], o.stop + pad_vox[d])) for d, o in enumerate(obj))
    near = {}
    for j in range(1, n_inst + 1):
        if j == k or union_vol[j] == 0 or j in merged_piece:
            continue
        uj = union_mask(j)[box]
        if not uj.any():
            continue
        dist = ndimage.distance_transform_edt(~uj, sampling=SPACING)
        dmin = float(dist[um[box]].min())
        if dmin <= FRAG_MM:
            near[j] = round(dmin, 2)
    inst['size_class'] = 'piece'
    inst['union_ml_before_merge'] = round(union_vol[k] * vox_ml, 2)
    ranked = sorted(near.items(), key=lambda kv: kv[1])
    # unambiguous when one instance is in reach, or the nearest is at least AMBIG_RATIO times closer than the next
    if len(ranked) == 1 or (len(ranked) >= 2 and ranked[1][1] >= AMBIG_RATIO * max(ranked[0][1], 0.5)):
        j = ranked[0][0]
        merged_piece[k] = j
        labels_k = {m: by_id[c]['label'] for m, c in inst['members'].items()}
        labels_j = {m: by_id[c]['label'] for m, c in instances[j - 1]['members'].items()}
        instances[j - 1].setdefault('fragments', []).append({'piece_labels': labels_k, 'volume_ml': round(union_vol[k] * vox_ml, 2), 'surface_distance_mm': near[j],
                                                              'next_instance_mm': ranked[1][1] if len(ranked) > 1 else None,
                                                              'same_labels_as_target': all(labels_j.get(m) == l for m, l in labels_k.items())})
        for c in inst['members'].values():
            assign[c] = (j - 1, 'fragment')
    elif near:
        inst['ambiguous_near'] = near
    else:
        inst['nearest_instance_mm'] = None
if merged_piece:
    for k, j in merged_piece.items():
        for m in models:
            inst_map[m][inst_map[m] == k] = j
    keep = [k for k in range(1, n_inst + 1) if k not in merged_piece]
    lut = np.zeros(n_inst + 1, np.uint8)
    for new, old in enumerate(keep, start=1):
        lut[old] = new
    for m in models:
        inst_map[m] = lut[inst_map[m]]
    instances = [instances[k - 1] for k in keep]
    remap = {old - 1: new - 1 for new, old in enumerate(keep, start=1)}
    for cid, (kk, st) in list(assign.items()):
        if st == 'fragment':
            assign[cid] = (remap[kk], st)
        else:
            assign[cid] = ([remap[x] for x in kk] if isinstance(kk, list) else remap[kk], st)
    for k, inst in enumerate(instances):
        inst['index'] = k + 1
        inst['id'] = f'{ID_PREFIX}{k + 1:02d}' if inst['role'] == MEMBER_ROLE else f'S{k + 1:02d}'
    print('pieces merged geometrically:', len(merged_piece), flush=True)

# 4. vote --------------------------------------------------------------------------------------------
n_inst = len(instances)
best_votes = np.zeros(ts.shape, np.uint8)
winner = np.zeros(ts.shape, np.uint8)
n_distinct = np.zeros(ts.shape, np.uint8)   # how many different instance ids the models put on a voxel (conflict when > 1)
for k in range(1, n_inst + 1):
    v = sum((inst_map[m] == k).astype(np.uint8) for m in models)
    better = v > best_votes
    winner[better] = k
    best_votes[better] = v[better]
    n_distinct += (v > 0).astype(np.uint8)
eligible = sum(processed[m].astype(np.uint8) for m in models)
sacrum_ids = [inst['index'] for inst in instances if inst['role'] == 'sacrum']
if sacrum_ids:
    sac_vox = np.isin(winner, sacrum_ids)
    for m in models:
        if not supports_sacrum[m]:
            eligible = eligible - (sac_vox & processed[m]).astype(np.uint8)
consensus = np.where((best_votes > 0) & (best_votes * 2 > eligible), winner, 0).astype(np.uint8)
review = np.where(best_votes > 0, winner, 0).astype(np.uint8)   # winner-takes-all view only; the per-model maps keep every alternative
print('instances', n_inst, 'consensus voxels', int((consensus > 0).sum()), 'review-only voxels', int(((review > 0) & (consensus == 0)).sum()),
      'conflict voxels', int((n_distinct > 1).sum()), flush=True)

# per-instance table
skelly_pelvis = sk == SK_PELVIS
for inst in instances:
    k = inst['index']
    cm = consensus == k
    rm = union_mask(k)                       # true union: every voxel where any model votes this instance
    votes_k = sum((inst_map[m] == k).astype(np.uint8) for m in models)
    n_c, n_r = int(cm.sum()), int(rm.sum())
    inst['consensus_ml'] = round(n_c * vox_ml, 2)
    inst['union_ml'] = round(n_r * vox_ml, 2)
    inst['agreement_ratio'] = round(n_c / n_r, 3) if n_r else None
    inst['unanimous_fraction'] = round(float((best_votes[cm] == eligible[cm]).mean()), 3) if n_c else None
    inst['eligible_models_on_consensus'] = {str(e): int((eligible[cm] == e).sum()) for e in np.unique(eligible[cm])} if n_c else {}
    inst['votes_histogram_on_union'] = {str(v): int((votes_k[rm] == v).sum()) for v in np.unique(votes_k[rm])} if n_r else {}
    inst['conflict_voxels'] = int(((n_distinct > 1) & rm).sum())            # union voxels where another model votes a different instance
    inst['lost_to_other_winner_ml'] = round(float((rm & (winner != k) & (winner > 0)).sum()) * vox_ml, 2)   # union voxels the winner map gives to another instance
    inst.setdefault('size_class', 'full' if n_r else 'empty')
    if n_c:
        c = np.array(ndimage.center_of_mass(cm))
        inst['consensus_centroid_ras_mm'] = to_ras(c).round(1).tolist()
        inst['consensus_centroid_vhf_mm'] = to_vhf(c).round(1).tolist()
        zr = np.nonzero(cm.any(axis=(0, 1)))[0]
        inst['consensus_z_vox'] = [int(zr[0] + off[2]), int(zr[-1] + off[2] + 1)]
        inst['crosses_skellytour_seam_z'] = [z for z in seams if inst['consensus_z_vox'][0] < z < inst['consensus_z_vox'][1]]
    inst['skellytour_pelvis_overlap_ml'] = round(float((rm & skelly_pelvis).sum()) * vox_ml, 2)
    inst['models'] = {}
    for m in models:
        cid = inst['members'].get(m)
        if cid is not None:
            st = assign[cid][1]
            im_ = inst_map[m] == k
            inter = int((im_ & cm).sum())
            iou = inter / (int(im_.sum()) + n_c - inter) if (im_.any() or n_c) else None
            inst['models'][m] = {'state': st, 'label': by_id[cid]['label'], 'candidate_ml': by_id[cid]['volume_ml'], 'components_of_label': by_id[cid]['components_of_label'],
                                 'iou_with_consensus': round(iou, 3) if iou is not None else None,
                                 'extra_candidates': [by_id[x]['label'] + f"#{by_id[x]['component']}" for x in inst.get('extra_cids', []) if by_id[x]['model'] == m],
                                 'seed_components': inst.get('seed_merged_from') if st == 'seed' else None}
        elif inst['role'] == 'sacrum' and not supports_sacrum[m]:
            inst['models'][m] = {'state': 'unsupported'}
        elif n_r and float(processed[m][rm].mean()) < 0.5:
            inst['models'][m] = {'state': 'unprocessed', 'processed_fraction': round(float(processed[m][rm].mean()), 3)}
        else:
            # absorbed into another label of the same model? (a body labelled sacrum or PELVIS is not a negative prediction)
            raw = arrays[m][0][rm] if n_r else np.zeros(0, np.uint8)
            other = raw[raw > 0]
            if n_r and len(other) / n_r >= 0.5:
                vals, cnt = np.unique(other, return_counts=True)
                top = int(vals[cnt.argmax()])
                inv = {v: k for k, v in arrays[m][1].items()}
                name = inv.get(top, 'PELVIS' if (m == 'skellytour' and top == SK_PELVIS) else f'label_{top}')
                inst['models'][m] = {'state': 'absorbed', 'absorbed_into': name, 'fraction_of_union': round(len(other) / n_r, 3)}
            else:
                inst['models'][m] = {'state': 'negative'}
    inst['source_labels'] = {m: v.get('label') for m, v in inst['models'].items() if v.get('label')}
    inst['name_status'] = 'pending'
    for key in ('members', 'seed_cids', 'group_cids', 'extra_cids'):
        inst.pop(key, None)
    if not inst.get('seed_merged_from'):
        inst.pop('seed_merged_from', None)
    if not inst.get('fragments'):
        inst.pop('fragments', None)

our_vert = [inst for inst in instances if inst['role'] == MEMBER_ROLE and inst['consensus_ml'] > 0 and inst['size_class'] == 'full']
pieces = [inst for inst in instances if inst['role'] == MEMBER_ROLE and inst['size_class'] == 'piece']
hra_evidence, lumbar_block = None, []
if FAMILY == 'vertebrae' and not NO_HRA:
    # 5. HRA same-donor chain (evidence, not decision) ------------------------------------------------------
    hra = json.loads((ROOT / 'public/atlases/hra-female.json').read_text())
    hra_names = {'vertebral bone 1': 'C1', 'vertebral bone 2': 'C2'}
    hra_names.update({f'mammalian cervical vertebra {i}': f'C{i}' for i in range(3, 8)})
    hra_names.update({f'thoracic vertebra {i}': f'T{i}' for i in range(1, 13)})
    hra_names.update({f'lumbar vertebra {i}': f'L{i}' for i in range(1, 7)})
    hra_names['fused sacrum'] = 'sacrum'
    hra_to_vhf = np.array(json.loads((ROOT / 'transforms/hra-stage-to-vhf.json').read_text())['matrix_row_major']).reshape(4, 4)
    stage_to_image = np.linalg.inv(np.array(json.loads((ROOT / 'transforms/source-to-stage.json').read_text())['denver-image-to-stage']['matrix_row_major']).reshape(4, 4))
    hra_chain = []
    for p in hra['parts']:
        if p['name'] in hra_names:
            c = (np.array(p['bounds'][0]) + np.array(p['bounds'][1])) / 2
            w = stage_to_image @ hra_to_vhf @ np.r_[c, 1]
            hra_chain.append({'name': hra_names[p['name']], 'asset': p['id'], 'vhf_mm': w[:3].round(1).tolist()})
    hra_chain.sort(key=lambda r: -r['vhf_mm'][2])
    hra_vert = [r for r in hra_chain if r['name'] != 'sacrum']
    hra_sacrum = next((r for r in hra_chain if r['name'] == 'sacrum'), None)
    our_vert = [inst for inst in instances if inst['role'] == MEMBER_ROLE and inst['consensus_ml'] > 0]
    our_sacrum = next((inst for inst in instances if inst['role'] == 'sacrum'), None)
    # match by order from the sacrum upwards: the lowest consensus vertebra <-> HRA L6, and so on
    hra_evidence = {'source': 'HRA united-female v1.5 (public/atlases/hra-female.json), modelled on the Visible Human Female; NIH 3D 3DPX-020988: "The Visible Human Female has 6 lumbar vertebrae"',
                    'transform': 'hra-stage-to-vhf (similarity on six organ proxies, RMS 7.4 mm) then inverse denver-image-to-stage; positions are approximate, the order and count are the evidence',
                    'hra_vertebra_count': len(hra_vert), 'our_consensus_vertebra_count': len(our_vert), 'hra_chain_vhf_mm': hra_chain,
                    'sacrum_offset_mm': None, 'by_order_from_sacrum': []}
    if hra_sacrum and our_sacrum and our_sacrum.get('consensus_centroid_vhf_mm'):
        hra_evidence['sacrum_offset_mm'] = round(float(np.linalg.norm(np.array(hra_sacrum['vhf_mm']) - np.array(our_sacrum['consensus_centroid_vhf_mm']))), 1)
    for n, inst in enumerate(reversed(our_vert)):   # caudal -> cranial
        h = hra_vert[len(hra_vert) - 1 - n] if n < len(hra_vert) else None
        row = {'instance': inst['id'], 'hra_name_by_order': h['name'] if h else None,
               'z_offset_mm': round(float(inst['consensus_centroid_vhf_mm'][2] - h['vhf_mm'][2]), 1) if h and inst.get('consensus_centroid_vhf_mm') else None}
        inst['hra_name_by_order'] = row['hra_name_by_order']
        inst['hra_z_offset_mm'] = row['z_offset_mm']
        hra_evidence['by_order_from_sacrum'].append(row)
    hra_evidence['by_order_from_sacrum'].reverse()
    hra_evidence['counts_agree'] = len(hra_vert) == len(our_vert)
    hra_evidence['reading'] = ('Same count as the HRA female skeleton: the by-order names are a candidate numbering with same-donor external support, pending anatomist confirmation.'
                               if hra_evidence['counts_agree'] else
                               f'Counts differ ({len(our_vert)} consensus vertebra instances against {len(hra_vert)} HRA vertebrae): by-order names are not usable until the difference is explained (missing instance, unprocessed region, or an HRA modelling choice).')
    print('HRA chain', len(hra_vert), 'vertebrae; ours', len(our_vert), '; counts agree', hra_evidence['counts_agree'], flush=True)

    # summary of the lumbar-type block: instances below the last one that any model calls T12
    lumbar_block = []
    t12_z = [inst['z_ras_mm'] for inst in instances if any(l.endswith('T12') for l in inst['source_labels'].values())]
    if t12_z:
        lumbar_block = [inst['id'] for inst in instances if inst['role'] == 'vertebra' and inst['z_ras_mm'] < min(t12_z) and inst['consensus_ml'] > 0]


# 6. write volumes and JSON -----------------------------------------------------------------------------
OUT_NII.mkdir(parents=True, exist_ok=True)
def save(name, arr_roi):
    full = np.zeros(ts_im.shape, np.uint8)
    full[roi] = arr_roi
    nib.save(nib.Nifti1Image(full, affine), OUT_NII / name)
save(f'{NII_STEM}-instances.nii.gz', consensus)
save(f'{NII_STEM}-review.nii.gz', review)
save(f'{NII_STEM}-votes.nii.gz', best_votes)
save(f'{NII_STEM}-eligible.nii.gz', eligible)
for m in models:   # every alternative is kept: instance id voted by each model
    save(f'{NII_STEM}-model-{m}.nii.gz', inst_map[m])

out = {'ct': CT, 'family': FAMILY, 'inputs': {'totalseg': rel(TS), 'moose': rel(MOOSE), 'skellytour': rel(SKELLY_DIR / 'skellytour_high.nii.gz'), 'ct_hu': rel(HU)},
       'grid': {'shape': list(ts_im.shape), 'axcodes': list(nib.aff2axcodes(affine)), 'voxel_ml': vox_ml, 'roi': [[s.start, s.stop] for s in roi]},
       'parameters': {'min_candidate_ml': MIN_ML, 'iou_group': IOU_GROUP, 'iou_match': IOU_MATCH, 'cover_part': COVER_PART, 'oversize': OVERSIZE, 'piece_ratio': PIECE_RATIO, 'fragment_mm': FRAG_MM,
                      'connectivity': 26, 'vote': 'strict majority of eligible models per voxel', 'tie_rule': 'winner map: equal votes go to the lower instance index (cranial); such voxels are never consensus and are counted in conflict_voxels',
                      'spacing_mm': SPACING.round(4).tolist(),
                      'eligibility': {'totalseg': 'whole grid', 'moose': 'whole grid', 'skellytour': f'body crop i {i0}:{i1} j {j0}:{j1} (plan.json); no sacrum class'}},
       'label_vocabulary': {'totalseg': sorted(TS_LABELS), 'moose': sorted(MO_LABELS), 'skellytour': sorted(SK_LABELS)},
       'candidates': cands, 'fragments_below_min': fragments, 'pairwise_correspondence': pairwise,
       'skellytour_manifest': skelly_manifest_info,
       'instances': instances, 'instance_count': {f'{MEMBER_ROLE}_consensus_full': len(our_vert), f'{MEMBER_ROLE}_pieces': len(pieces),
                                                   f'{MEMBER_ROLE}_any': sum(1 for i in instances if i['role'] == MEMBER_ROLE), 'sacrum': len(sacrum_ids),
                                                   'conflict_voxels': int((n_distinct > 1).sum())},
       'lumbar_type_block_below_T12': lumbar_block, 'hra_same_donor_evidence': hra_evidence,
       'skellytour_seams_z': seams,
       'volumes': {k: rel(OUT_NII / f'{NII_STEM}-{k}.nii.gz') for k in ['instances', 'review', 'votes', 'eligible'] + [f'model-{m}' for m in models]},
       'naming': 'Every instance id is provisional and geometric. hra_name_by_order is external same-donor evidence for the count and order, not a decision; name_status stays pending until an anatomist or a documented reference confirms the levels.'}
OUT_JSON.write_text(json.dumps(out, indent=1, default=float) + '\n')
print('->', rel(OUT_JSON), flush=True)

# 7. panels ---------------------------------------------------------------------------------------------
def make_panels():
    import matplotlib  # noqa: E402
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt  # noqa: E402
    from matplotlib import colors  # noqa: E402

    OUT_PNG.mkdir(parents=True, exist_ok=True)
    hu = np.asanyarray(nib.load(HU).dataobj)[roi].astype(np.float32)
    T = ornt_transform(io_orientation(affine), axcodes2ornt(('R', 'A', 'S')))
    R = lambda a: apply_orientation(a, T)   # noqa: E731
    hu_r, cons_r, rev_r = R(hu), R(consensus), R(review)
    mod_r = {m: R(arrays[m][0]) for m in models}
    votes_r, elig_r = R(best_votes), R(eligible)
    # seam z (voxel index along the original k axis) -> RAS-array index
    flip_k = T[2, 1] < 0
    seam_idx = [(ts.shape[2] - 1 - (z - off[2])) if flip_k else (z - off[2]) for z in seams if off[2] <= z < off[2] + ts.shape[2]]
    cmap = colors.ListedColormap(plt.get_cmap('tab20').colors + plt.get_cmap('tab20b').colors)
    norm = colors.BoundaryNorm(np.arange(0.5, n_inst + 1.5), cmap.N)
    occ = np.argwhere(cons_r > 0)
    x_mid = int(np.median(occ[:, 0])) if len(occ) else cons_r.shape[0] // 2
    y_mid = int(np.median(occ[:, 1])) if len(occ) else cons_r.shape[1] // 2
    sp = np.abs(np.diag(affine)[:3])
    aspect_sag = sp[2] / sp[1]
    aspect_cor = sp[2] / sp[0]


    def centroid_r(inst_index, arr=cons_r):
        m = arr == inst_index
        return np.array(ndimage.center_of_mass(m)) if m.any() else None


    def overlay(ax, img, lab, aspect, title):
        ax.imshow(img.T, cmap='gray', vmin=-200, vmax=1200, origin='lower', aspect=aspect)
        ax.imshow(np.ma.masked_equal(lab.T, 0), cmap=cmap, norm=norm, alpha=0.55, origin='lower', aspect=aspect, interpolation='nearest')
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
        for z in seam_idx:
            ax.axhline(z, color='cyan', lw=0.6, ls='--')


    # sagittal: max-projection of the instance labels over a slab around the mid-sagittal plane keeps thin bodies visible
    slab = slice(max(0, x_mid - 12), min(cons_r.shape[0], x_mid + 12))
    def slab_labels(lab):
        if FAMILY != 'vertebrae':   # ribs: coronal projection along y (anterior-posterior), labels of the most posterior voxel win
            out = np.zeros((lab.shape[0], lab.shape[2]), lab.dtype)
            for dy in range(lab.shape[1] - 1, -1, -1):
                m = lab[:, dy, :] > 0
                out[m] = lab[:, dy, :][m]
            return out
        s = lab[slab]
        # per (y, z) take the label of the voxel nearest to the mid plane
        out = np.zeros(s.shape[1:], lab.dtype)
        for dx in sorted(range(s.shape[0]), key=lambda i: abs(i - (x_mid - slab.start)), reverse=True):
            m = s[dx] > 0
            out[m] = s[dx][m]
        return out
    if FAMILY != 'vertebrae':
        hu_r_view = hu_r.max(axis=1)     # coronal MIP of the CT for the rib panels
        aspect_sag = aspect_cor
    else:
        hu_r_view = hu_r[x_mid]

    fig, ax = plt.subplots(figsize=(6, 16))
    overlay(ax, hu_r_view, slab_labels(cons_r), aspect_sag, f'{CT} {FAMILY}: consensus instances (strict majority), ' + ('sagittal slab' if FAMILY == 'vertebrae' else 'coronal projection') + '; cyan = Skellytour chunk seams')
    for inst in instances:
        if inst['consensus_ml'] <= 0:
            continue
        c = centroid_r(inst['index'])
        if c is not None:
            hn = inst.get('hra_name_by_order')
            ax.text((c[1] if FAMILY == 'vertebrae' else c[0]) + 25, c[2], f"{inst['id']}  {inst['consensus_ml']:.0f} mL  {inst['unanimous_fraction']:.2f}" + (f'  HRA {hn}' if hn else ''), fontsize=6, color='yellow', va='center')
    fig.tight_layout()
    fig.savefig(OUT_PNG / 'sagittal.png', dpi=130)
    plt.close(fig)

    # models: each model's own labels with its own names, then the consensus
    fig, axes = plt.subplots(1, 4, figsize=(20, 16) if FAMILY == 'vertebrae' else (24, 14))
    for ax, m in zip(axes, models):
        lab = slab_labels(mod_r[m])
        ids = arrays[m][1]
        inv = {v: k for k, v in ids.items()}
        show = np.zeros_like(lab)
        for v in np.unique(lab):
            if v in inv:
                show[lab == v] = v
        ax.imshow(hu_r_view.T, cmap='gray', vmin=-200, vmax=1200, origin='lower', aspect=aspect_sag)
        ax.imshow(np.ma.masked_equal(show.T, 0), cmap='nipy_spectral', alpha=0.55, origin='lower', aspect=aspect_sag, interpolation='nearest')
        for z in seam_idx:
            ax.axhline(z, color='cyan', lw=0.6, ls='--')
        for v in np.unique(show):
            if v and v in inv:
                c = np.array(ndimage.center_of_mass(show == v))
                ax.text(c[0] + 25, c[1], inv[v].replace('vertebrae_', '').replace('vertebra_', '').replace(f'rib_{SIDE}_', 'r').replace(f'{str(SIDE).upper()}_RIB_', 'R'), fontsize=6, color='yellow', va='center')
        ax.set_title(f'{m}: own labels', fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    overlay(axes[3], hu_r_view, slab_labels(cons_r), aspect_sag, 'consensus instances')
    for inst in instances:
        c = centroid_r(inst['index'])
        if c is not None:
            axes[3].text((c[1] if FAMILY == 'vertebrae' else c[0]) + 25, c[2], inst['id'], fontsize=6, color='yellow', va='center')
    fig.tight_layout()
    fig.savefig(OUT_PNG / 'models.png', dpi=110)
    plt.close(fig)

    # coronal
    fig, ax = plt.subplots(figsize=(8, 16))
    cor = np.zeros(cons_r.shape[::2], cons_r.dtype)
    for dy in range(max(0, y_mid - 15), min(cons_r.shape[1], y_mid + 15)):
        m = cons_r[:, dy, :] > 0
        cor[m] = cons_r[:, dy, :][m]
    overlay(ax, hu_r[:, y_mid, :], cor, aspect_cor, f'{CT}: consensus instances, coronal slab')
    for inst in instances:
        c = centroid_r(inst['index'])
        if c is not None:
            ax.text(c[0] + 30, c[2], inst['id'], fontsize=6, color='yellow', va='center')
    fig.tight_layout()
    fig.savefig(OUT_PNG / 'coronal.png', dpi=130)
    plt.close(fig)

    # axial: one tile per instance at its consensus centroid, consensus fill + model contours
    shown = [inst for inst in instances if inst['consensus_ml'] > 0]
    cols = 6
    rows = int(np.ceil(len(shown) / cols)) or 1
    fig, axes = plt.subplots(rows, cols, figsize=(3 * cols, 3 * rows))
    axes = np.atleast_1d(axes).ravel()
    colours = {'totalseg': 'red', 'moose': 'lime', 'skellytour': 'deepskyblue'}
    inst_r = {m: R(inst_map[m]) for m in models}
    for ax in axes:
        ax.axis('off')
    for ax, inst in zip(axes, shown):
        c = centroid_r(inst['index'])
        z = int(round(c[2]))
        half = 45
        xs = slice(max(0, int(c[0]) - half), int(c[0]) + half)
        ys = slice(max(0, int(c[1]) - half), int(c[1]) + half)
        ax.imshow(hu_r[xs, ys, z].T, cmap='gray', vmin=-200, vmax=1200, origin='lower')
        ax.imshow(np.ma.masked_not_equal(cons_r[xs, ys, z].T, inst['index']), cmap=cmap, norm=norm, alpha=0.4, origin='lower', interpolation='nearest')
        for m in models:
            lab = inst_r[m][xs, ys, z]
            if (lab == inst['index']).any():
                ax.contour((lab == inst['index']).T.astype(float), levels=[0.5], colors=colours[m], linewidths=0.8)
        st = ' '.join(f"{m[:2]}:{inst['models'][m]['state'][:4]}" for m in models)
        ax.set_title(f"{inst['id']} z{inst['consensus_z_vox'][0]}-{inst['consensus_z_vox'][1]} {inst['consensus_ml']:.0f} mL\n{st}", fontsize=7)
    fig.suptitle(f'{CT}: axial at each instance centroid; fill = consensus; contours: red TotalSegmentator, green MOOSE, blue Skellytour', fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT_PNG / 'axial.png', dpi=110)
    plt.close(fig)
    print('panels ->', rel(OUT_PNG), flush=True)



if NO_PANELS:
    print('panels skipped', flush=True)
else:
    make_panels()

# 8. self-test of the correspondence states on perturbed copies of the MOOSE candidates -----------------------
if SELFTEST:
    other = max(['moose', 'skellytour'], key=lambda m: sum(1 for r in pairwise[f'totalseg|{m}']['b_to_a'].values() if r['state'] == 'matched'))
    print(f'selftest: perturbing {other} candidates against TotalSegmentator', flush=True)
    ts_c = [c for c in cands if c['model'] == 'totalseg']
    mo_c = [c for c in cands if c['model'] == other]
    base = pairwise[f'totalseg|{other}']
    matched_mo = [r for r in base['b_to_a'].values() if r['state'] == 'matched']
    matched_mo.sort(key=lambda r: -r['z_ras_mm'])
    assert len(matched_mo) >= 6, 'need at least six matched candidates for the self-test'
    mid = len(matched_mo) // 2
    pick = matched_mo[mid - 2:mid + 2]   # four consecutive matched bodies from the middle of the chain
    ids = [r['cid'] for r in pick]
    pm = cand_map[other].copy()
    results = {}
    # (a) merge: two neighbours get one id -> expect 'split' on the merged MOOSE candidate, 'merge' on both TS partners
    pm_a = pm.copy()
    pm_a[pm_a == ids[1]] = ids[0]
    fake = [dict(c) for c in mo_c if c['cid'] != ids[1]]
    for c in fake:
        if c['cid'] == ids[0]:
            c['voxels'] = by_id[ids[0]]['voxels'] + by_id[ids[1]]['voxels']
    r = correspondence(cand_map['totalseg'], pm_a, ts_c, fake)
    merged_state = next(v['state'] for v in r['b_to_a'].values() if v['cid'] == ids[0])
    ts_partners = [v['state'] for v in r['a_to_b'].values() if v['partners'] and v['partners'][0]['cid'] == ids[0]]
    results['merge_two_bodies'] = {'moose_state': merged_state, 'totalseg_states': ts_partners, 'pass': merged_state == 'split' and ts_partners and all(s == 'merge' for s in ts_partners)}
    # (b) split: one body cut in two along z -> the two halves are 'merge' against TS, TS partner is 'split'
    pm_b = pm.copy()
    box = by_id[ids[2]]['box']
    zc = (box[2][0] + box[2][1]) // 2
    half_id = max(by_id) + 1
    sub = pm_b[:, :, zc:]
    sub[sub == ids[2]] = half_id
    fake = [dict(c) for c in mo_c]
    n_hi = int((pm_b == half_id).sum())
    for c in fake:
        if c['cid'] == ids[2]:
            c['voxels'] -= n_hi
    fake.append(dict(by_id[ids[2]], cid=half_id, voxels=n_hi, component=99, label=by_id[ids[2]]['label']))
    by_id[half_id] = fake[-1]
    r = correspondence(cand_map['totalseg'], pm_b, ts_c, fake)
    halves = [v['state'] for v in r['b_to_a'].values() if v['cid'] in (ids[2], half_id)]
    ts_state = next(v['state'] for v in r['a_to_b'].values() if v['partners'] and v['partners'][0]['cid'] in (ids[2], half_id))
    results['split_one_body'] = {'moose_states': halves, 'totalseg_state': ts_state, 'pass': all(s == 'merge' for s in halves) and ts_state == 'split'}
    del by_id[half_id]
    # (c) delete: a body removed -> its TS partner becomes 'unmatched'
    pm_c = pm.copy()
    pm_c[pm_c == ids[3]] = 0
    fake = [c for c in mo_c if c['cid'] != ids[3]]
    r = correspondence(cand_map['totalseg'], pm_c, ts_c, fake)
    lost = [v['state'] for v in base['a_to_b'].values() if v['partners'] and v['partners'][0]['cid'] == ids[3]]
    now = [r['a_to_b'][k]['state'] for k, v in base['a_to_b'].items() if v['partners'] and v['partners'][0]['cid'] == ids[3]]
    results['delete_one_body'] = {'before': lost, 'after': now, 'pass': all(s == 'unmatched' for s in now)}
    # (d) rename: swapping the *names* of two MOOSE candidates changes no geometry -> states and order unchanged (names are never used)
    fake = [dict(c) for c in mo_c]
    for c in fake:
        if c['cid'] == ids[0]:
            c['label'] = by_id[ids[1]]['label']
        elif c['cid'] == ids[1]:
            c['label'] = by_id[ids[0]]['label']
    r = correspondence(cand_map['totalseg'], pm, ts_c, fake)
    results['swap_two_labels'] = {'state_counts_before': base['state_counts']['a_to_b'], 'state_counts_after': r['state_counts']['a_to_b'],
                                  'order_violations_before': base['order']['order_violations'], 'order_violations_after': r['order']['order_violations'],
                                  'pass': r['state_counts'] == base['state_counts'] and r['order'] == base['order']}
    # (e) shift: one body moved 15 mm caudally -> IoU with its TS partner drops below the match threshold ('partial') or the order breaks
    pm_e = pm.copy()
    shift = int(round(15 / SPACING[2]))
    m = pm == ids[1]
    pm_e[m] = 0
    moved = np.zeros_like(m)
    moved[:, :, :-shift] = m[:, :, shift:]
    pm_e[moved & (pm_e == 0)] = ids[1]
    r = correspondence(cand_map['totalseg'], pm_e, ts_c, mo_c)
    shifted = next(v['state'] for v in r['b_to_a'].values() if v['cid'] == ids[1])
    results['shift_15mm'] = {'moose_state': shifted, 'pass': shifted != 'matched'}
    results['all_pass'] = all(v['pass'] for k, v in results.items() if k != 'all_pass')
    results['perturbed_model'] = other
    out['selftest'] = results
    OUT_JSON.write_text(json.dumps(out, indent=1, default=float) + '\n')
    for k, v in results.items():
        print('selftest', k, v if k in ('all_pass', 'perturbed_model') else v['pass'], flush=True)
    if not results['all_pass']:
        sys.exit('selftest failed')
