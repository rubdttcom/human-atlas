"""Consensus and laterality check of the open CT bone priors (plan B, stage 1).

Compares, on one whole-body CT of the VHF donor, the bone labels of up to three models that ran
on the same voxel grid: TotalSegmentator `total`, MOOSE (`clin_ct_peripheral_bones`,
`clin_ct_vertebrae`, `clin_ct_ribs`) and Skellytour `high` (optional, when its file exists).

Usage: python scripts/ct-prior-consensus.py nlm | denver

Per bone (the shared naming below): volume per model, pairwise Dice, centroid offsets in mm, and
the consensus class: `agree` (all pairwise Dice >= 0.80), `partial`, `disagree` (a pair below 0.50),
`single` (one model only). Per bone and model the status is also recorded: `present`, `negative`
(the model has the class and processed the region but predicted nothing), `unsupported` (no such class)
or `unprocessed` (Skellytour ran on a body-cropped grid; outside the crop nothing was predicted).
Vertebrae are also matched by nearest centroid per label. That block is DIAGNOSTIC ONLY: it is not
one-to-one (two labels can pick the same partner: Denver totalseg|skellytour L2 and L3 both pick L2),
so it must not be used as a correspondence for voting. The instance correspondence lives in
`scripts/ct-vertebra-instances.py`. The name lists below are the models' label vocabularies, not a
statement about how many vertebrae this donor has (she has six lumbar-type bodies; see the instance script).

Laterality. Three consistency checks, all in the NIfTI RAS world of the CT (+x = subject right). They are
not independent: checks 1 and 3 use TotalSegmentator organ labels and all three share the CT header
and the same models' training biases; together they show the placement is self-consistent, which is
anatomical evidence only as far as the organ labels are right (liver right, spleen left).
  1. organ anchor (TotalSegmentator only): liver and gallbladder centroids must have x > 0,
     spleen and stomach x < 0; this fixes which image side is the subject's right, independent of
     any bone label;
  2. every paired bone label of every model: `*_left` centroid x < 0 and `*_right` x > 0;
  3. Denver CT only: the same centroids carried by transforms/denver-aligned-ct-voxel-to-vhf.json
     into the Denver image frame (+x subject right, canonical space VHF-image-2022) must fall on the
     side of the Denver `Left` / `Right` meshes of the same bone (femur, pelvis, patella, tibia).
     This resolves the mirror ambiguity of the pelvis-only ICP placement (flips [-1,1,1] p95 5.4 mm
     versus [1,1,1] p95 6.5 mm): the two candidates differ in handedness, and only one puts the
     liver on the side of the Denver right pelvis.

Output: generated/ct-prior-consensus-<ct>.json
"""
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
CT = sys.argv[1] if len(sys.argv) > 1 else 'nlm'

if CT == 'nlm':
    TS = ROOT / 'data/derived/nlm-vhf/totalseg.nii'
    MOOSE = ROOT / 'data/derived/nlm-vhf/moose/segmentations'
    MOOSE_TAG = 'CT_vhf'
    SKELLY = ROOT / 'data/derived/nlm-vhf/skellytour/skellytour_high.nii.gz'
    VOX_TO_VHF = None
elif CT == 'denver':
    TS = ROOT / 'data/derived/denver/priors/totalseg/total.nii.gz'
    MOOSE = next((ROOT / 'data/derived/denver/priors/moose').glob('*/segmentations'))
    MOOSE_TAG = 'CT_denverct'
    SKELLY = ROOT / 'data/derived/denver/priors/skellytour/skellytour_high.nii.gz'
    VOX_TO_VHF = np.array(json.loads((ROOT / 'transforms/denver-aligned-ct-voxel-to-vhf.json').read_text())['matrix_row_major']).reshape(4, 4)
else:
    sys.exit('usage: ct-prior-consensus.py nlm|denver')

CLASSMAP = {v: int(k) for k, v in json.loads((ROOT / 'data/derived/nlm-vhf/totalseg-classmap.json').read_text())['total'].items()}
VERT = [f'C{i}' for i in range(1, 8)] + [f'T{i}' for i in range(1, 13)] + [f'L{i}' for i in range(1, 6)]   # shared label vocabulary of the three models, NOT the donor's count (MOOSE also has L6, TotalSegmentator S1)
SKELLY_LABELS = {'SKULL': 1, 'PELVIS': 2, 'STERNUM': 3, 'LEFT_FEMUR': 4, 'RIGHT_FEMUR': 5, 'LEFT_HUMERUS': 6, 'RIGHT_HUMERUS': 7,
                 'LEFT_SCAPULA': 8, 'RIGHT_SCAPULA': 9, 'LEFT_CLAVICLE': 10, 'RIGHT_CLAVICLE': 11}
SKELLY_LABELS.update({f'LEFT_RIB_{i}': 11 + i for i in range(1, 13)})
SKELLY_LABELS.update({f'RIGHT_RIB_{i}': 23 + i for i in range(1, 13)})
SKELLY_LABELS.update({f'VERT_{i}': 35 + i for i in range(1, 25)})   # VERT_1 = C1 ... VERT_24 = L5 (checked by centroid below)

# shared bone names -> (totalseg label, moose (model, label), skellytour label)
SHARED = {}
for side in ['left', 'right']:
    S = side.upper()
    SHARED[f'femur_{side}'] = (f'femur_{side}', ('peripheral_bones', f'femur_{side}'), f'{S}_FEMUR')
    SHARED[f'humerus_{side}'] = (f'humerus_{side}', ('peripheral_bones', f'humerus_{side}'), f'{S}_HUMERUS')
    SHARED[f'scapula_{side}'] = (f'scapula_{side}', ('peripheral_bones', f'scapula_{side}'), f'{S}_SCAPULA')
    SHARED[f'clavicle_{side}'] = (f'clavicula_{side}', ('peripheral_bones', f'clavicle_{side}'), f'{S}_CLAVICLE')
    SHARED[f'hip_{side}'] = (f'hip_{side}', ('vertebrae', f'hip_{side}'), None)
    for i in range(1, 13):
        SHARED[f'rib_{side}_{i}'] = (f'rib_{side}_{i}', ('ribs', f'rib_{side}_{i}'), f'{S}_RIB_{i}')
    for b in ['patella', 'tibia', 'fibula', 'radius', 'ulna']:
        SHARED[f'{b}_{side}'] = (None, ('peripheral_bones', f'{b}_{side}'), None)   # MOOSE only; TotalSegmentator ships these in a licensed task
SHARED['skull'] = ('skull', ('peripheral_bones', 'skull'), 'SKULL')
SHARED['sternum'] = ('sternum', ('ribs', 'sternum'), 'STERNUM')
SHARED['sacrum'] = ('sacrum', ('vertebrae', 'sacrum'), None)
for n, v in enumerate(VERT, start=1):
    SHARED[f'vertebra_{v}'] = (f'vertebrae_{v}', ('vertebrae', f'vertebra_{v}'), f'VERT_{n}')
SHARED['pelvis'] = (None, None, 'PELVIS')   # Skellytour merges both hips and the sacrum


def load(path):
    im = nib.load(path)
    a = np.asanyarray(im.dataobj)
    a = a.astype(np.uint8) if a.max() < 256 else a.astype(np.int16)
    return im, a


class Model:
    """One label volume with per-label bounding boxes, volumes and centroids computed in one pass."""

    def __init__(self, name, arr, affine, names_to_ids):
        self.name, self.arr, self.affine = name, arr, affine
        self.ids = names_to_ids
        self.processed_box = None   # None = whole grid; else the slices the model actually saw
        self.vox_ml = float(np.prod(np.abs(np.diag(affine)[:3])) / 1000)
        objs = ndimage.find_objects(arr)
        self.box = {i + 1: o for i, o in enumerate(objs) if o is not None}
        self.info = {}
        for label, i in names_to_ids.items():
            o = self.box.get(i)
            if o is None:
                continue
            m = arr[o] == i
            n = int(m.sum())
            c = np.array(ndimage.center_of_mass(m)) + np.array([s.start for s in o])
            w = affine @ np.r_[c, 1]
            self.info[label] = {'voxels': n, 'volume_ml': round(n * self.vox_ml, 2), 'centroid_vox': c.tolist(), 'centroid_ras_mm': w[:3].tolist()}

    def mask(self, label, box):
        i = self.ids[label]
        return self.arr[box] == i

    def has(self, label):
        return label in self.info


def union_box(boxes):
    return tuple(slice(min(b[d].start for b in boxes), max(b[d].stop for b in boxes)) for d in range(3))


def dice(m1, l1, m2, l2):
    b = union_box([m1.box[m1.ids[l1]], m2.box[m2.ids[l2]]])
    a, c = m1.mask(l1, b), m2.mask(l2, b)
    inter = int((a & c).sum())
    return 2 * inter / (int(a.sum()) + int(c.sum()))


print('loading', CT, flush=True)
ts_im, ts_arr = load(TS)
affine = ts_im.affine


def same_grid(path, im):
    """Every model must sit on the TotalSegmentator voxel grid: same shape and the same affine (1e-3 mm), else the Dice values are meaningless."""
    if im.shape != ts_im.shape:
        sys.exit(f'{path}: shape {im.shape} differs from TotalSegmentator {ts_im.shape}')
    if not np.allclose(im.affine, affine, atol=1e-3):
        sys.exit(f'{path}: affine differs from TotalSegmentator (max |diff| {np.abs(im.affine - affine).max():.4f}); resample before comparing')

models = {}
models['totalseg'] = Model('totalseg', ts_arr, affine, CLASSMAP)
moose_arrays, moose_ids = {}, {}
for task in ['peripheral_bones', 'vertebrae', 'ribs']:
    f = MOOSE / f'clin_CT_{task}_segmentation_{MOOSE_TAG}.nii.gz'
    im, a = load(f)
    same_grid(f, im)
    ids = {v['name']: int(k) for k, v in json.loads((MOOSE / f'clin_CT_{task}_organ_indices.json').read_text())['organ_indices'].items()}
    models[f'moose:{task}'] = Model(f'moose:{task}', a, affine, ids)
if SKELLY.exists():
    im, a = load(SKELLY)
    same_grid(SKELLY, im)
    models['skellytour'] = Model('skellytour', a, affine, SKELLY_LABELS)
    plan = json.loads((SKELLY.parent / 'plan.json').read_text())
    i0, i1, j0, j1 = plan['crop']
    models['skellytour'].processed_box = (slice(i0, i1), slice(j0, j1), slice(0, a.shape[2]))   # outside the crop Skellytour saw nothing
    print('skellytour included, processed crop', plan['crop'], flush=True)
else:
    print('skellytour absent:', SKELLY.relative_to(ROOT), flush=True)
print('models ready', flush=True)


def resolve(bone):
    """(model, label) pairs available for a shared bone name, plus the status of every model on that bone.

    Status: `present`; `unsupported` (the model has no class for this bone: it cannot vote, it abstains);
    `unprocessed` (the model has the class but never saw the region where the other models put the bone);
    `negative` (the model has the class, saw the region and predicted nothing: a vote against, not an abstention).
    """
    ts, mo, sk = SHARED[bone]
    out, status = [], {}
    wanted = [('totalseg', ts), (f'moose:{mo[0]}' if mo else None, mo[1] if mo else None), ('skellytour', sk)]
    for m, label in wanted:
        if m is None or label is None or m not in models:
            status[(m or 'moose').split(':')[0]] = 'unsupported'
            continue
        if label not in models[m].ids:
            status[m.split(':')[0]] = 'unsupported'
        elif models[m].has(label):
            out.append((m, label))
            status[m.split(':')[0]] = 'present'
        else:
            status[m.split(':')[0]] = 'absent'   # refined below once the other models say where the bone is
    for m in list(status):
        if status[m] != 'absent':
            continue
        model = models[m if m != 'moose' else f'moose:{mo[0]}']
        if model.processed_box is not None and out:
            c = np.array(models[out[0][0]].info[out[0][1]]['centroid_vox'])
            inside = all(model.processed_box[d].start <= c[d] < model.processed_box[d].stop for d in range(3))
            status[m] = 'negative' if inside else 'unprocessed'
        else:
            status[m] = 'negative'
    return out, status


bones = {}
for bone in SHARED:
    avail, status = resolve(bone)
    if not avail:
        continue
    entry = {'models': {}, 'pairs': {}, 'model_status': status}
    for m, l in avail:
        entry['models'][m.split(':')[0]] = dict(label=l, **models[m].info[l])
    dices = []
    for i in range(len(avail)):
        for j in range(i + 1, len(avail)):
            (m1, l1), (m2, l2) = avail[i], avail[j]
            d = dice(models[m1], l1, models[m2], l2)
            c1, c2 = np.array(models[m1].info[l1]['centroid_ras_mm']), np.array(models[m2].info[l2]['centroid_ras_mm'])
            entry['pairs'][f"{m1.split(':')[0]}|{m2.split(':')[0]}"] = {'dice': round(d, 4), 'centroid_offset_mm': round(float(np.linalg.norm(c1 - c2)), 2)}
            dices.append(d)
    if not dices:
        entry['consensus'] = 'single'
    elif min(dices) >= 0.80:
        entry['consensus'] = 'agree'
    elif min(dices) < 0.50:
        entry['consensus'] = 'disagree'
    else:
        entry['consensus'] = 'partial'
    bones[bone] = entry
    print(f"{bone:16s} {entry['consensus']:9s} " + '  '.join(f"{k} {v['dice']:.3f}" for k, v in entry['pairs'].items()), flush=True)

# vertebra naming by nearest centroid: DIAGNOSTIC ONLY (not one-to-one; see docstring and ct-vertebra-instances.py)
vert_models = {'totalseg': [(f'vertebrae_{v}', v) for v in VERT], 'moose:vertebrae': [(f'vertebra_{v}', v) for v in VERT]}
if 'skellytour' in models:
    vert_models['skellytour'] = [(f'VERT_{n}', v) for n, v in enumerate(VERT, start=1)]
vert_centroids = {m: {v: np.array(models[m].info[l]['centroid_ras_mm']) for l, v in labels if models[m].has(l)} for m, labels in vert_models.items()}
vertebra_matching = {}
names = list(vert_centroids)
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        a, b = names[i], names[j]
        rows = {}
        shifts = []
        for v, c in vert_centroids[a].items():
            if not vert_centroids[b]:
                continue
            best = min(vert_centroids[b].items(), key=lambda kv: np.linalg.norm(kv[1] - c))
            rows[v] = {'nearest': best[0], 'distance_mm': round(float(np.linalg.norm(best[1] - c)), 2), 'same_name': best[0] == v}
            shifts.append(VERT.index(best[0]) - VERT.index(v))
        targets = [r['nearest'] for r in rows.values()]
        vertebra_matching[f"{a.split(':')[0]}|{b.split(':')[0]}"] = {'per_vertebra': rows, 'same_name_count': sum(r['same_name'] for r in rows.values()), 'n': len(rows),
                                                                    'shift_histogram': {str(s): shifts.count(s) for s in sorted(set(shifts))},
                                                                    'not_one_to_one': sorted({t for t in targets if targets.count(t) > 1}),
                                                                    'note': 'nearest centroid per label, diagnostic only; not a correspondence for voting (see ct-vertebra-instances.py)'}
        print('vertebra match', a, b, 'same name', sum(r['same_name'] for r in rows.values()), '/', len(rows), 'shifts', vertebra_matching[f"{a.split(':')[0]}|{b.split(':')[0]}"]['shift_histogram'], flush=True)

# laterality
lat = {'ras_convention': '+x = subject right (NIfTI RAS world of the CT affine)', 'organ_anchor': {}, 'bone_sides': {}, 'summary': {}}
anchor_ok = []
for organ, expect in [('liver', 'right'), ('gallbladder', 'right'), ('spleen', 'left'), ('stomach', 'left'), ('heart', 'left')]:
    if models['totalseg'].has(organ):
        x = models['totalseg'].info[organ]['centroid_ras_mm'][0]
        side = 'right' if x > 0 else 'left'
        lat['organ_anchor'][organ] = {'x_ras_mm': round(x, 1), 'expected_side': expect, 'observed_side': side, 'ok': side == expect}
        anchor_ok.append(side == expect)
# the heart sits left of the midline only slightly; report it but do not let it decide.
# The anchor needs at least one right-sided and one left-sided organ present; with no anchors the check is undecided, never passed.
anchors = {k: v for k, v in lat['organ_anchor'].items() if k != 'heart'}
has_both = any(v['expected_side'] == 'right' for v in anchors.values()) and any(v['expected_side'] == 'left' for v in anchors.values())
lat['summary']['organ_anchor_ok'] = bool(anchors) and has_both and all(v['ok'] for v in anchors.values())
lat['summary']['organ_anchor_n'] = len(anchors)
lat['summary']['midline_assumption'] = 'x = 0 of the CT RAS frame is taken as the midline; valid only because the anchors and the paired bones straddle it (checked by the bone-side test)'
for m, model in models.items():
    rows = {}
    for label in model.info:
        low = label.lower()
        if 'left' in low:
            expect = 'left'
        elif 'right' in low:
            expect = 'right'
        else:
            continue
        x = model.info[label]['centroid_ras_mm'][0]
        side = 'right' if x > 0 else 'left'
        rows[label] = {'x_ras_mm': round(x, 1), 'expected_side': expect, 'observed_side': side, 'ok': side == expect}
    lat['bone_sides'][m] = {'labels': rows, 'mismatches': [k for k, v in rows.items() if not v['ok']], 'n': len(rows)}
    print('laterality', m, 'mismatches', lat['bone_sides'][m]['mismatches'], '/', len(rows), flush=True)

if VOX_TO_VHF is not None:
    denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
    stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
    stage_to_image = np.linalg.inv(np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4))
    buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in denver['chunks']]
    denver_centroid = {}
    for p in denver['parts']:
        md = p['source_metadata']
        if md['source_label'] in ('Femur', 'Pelvis', 'Patella', 'Tibia', 'Fibula', 'Talus'):
            v = np.frombuffer(buffers[p['chunk']], '<f4', count=p['vertexCount'] * 3, offset=p['positions']).reshape(-1, 3).astype(float)
            c = v.mean(axis=0)
            denver_centroid[f"{md['source_label']}/{md['source_folder']}"] = (stage_to_image @ np.r_[c, 1])[:3]
    mid_x = float(np.mean([denver_centroid['Pelvis/Left'][0], denver_centroid['Pelvis/Right'][0]]))
    denver_right_positive = denver_centroid['Pelvis/Right'][0] > denver_centroid['Pelvis/Left'][0]
    rows = {}
    pairs = [('femur_left', 'Femur/Left'), ('femur_right', 'Femur/Right'), ('hip_left', 'Pelvis/Left'), ('hip_right', 'Pelvis/Right'),
             ('patella_left', 'Patella/Left'), ('patella_right', 'Patella/Right'), ('tibia_left', 'Tibia/Left'), ('tibia_right', 'Tibia/Right')]
    for bone, part in pairs:
        if bone not in bones or part not in denver_centroid:
            continue
        for m, info in bones[bone]['models'].items():
            c = VOX_TO_VHF @ np.r_[info['centroid_vox'], 1]
            d = denver_centroid[part]
            same_side = (c[0] - mid_x) * (d[0] - mid_x) > 0
            rows[f'{bone}@{m}'] = {'ct_in_denver_frame_mm': c[:3].round(1).tolist(), 'denver_mesh_mm': d.round(1).tolist(), 'denver_part': part,
                                    'offset_mm': round(float(np.linalg.norm(c[:3] - d)), 1), 'same_side_as_denver_mesh': bool(same_side)}
    # organ anchor carried into the Denver frame: liver must lie on the side of the Denver right pelvis
    organ_rows = {}
    for organ, expect_part in [('liver', 'Pelvis/Right'), ('spleen', 'Pelvis/Left')]:
        if models['totalseg'].has(organ):
            c = VOX_TO_VHF @ np.r_[models['totalseg'].info[organ]['centroid_vox'], 1]
            organ_rows[organ] = {'x_denver_mm': round(float(c[0]), 1), 'midline_x_mm': round(mid_x, 1), 'expected_side_of': expect_part,
                                 'ok': bool((c[0] - mid_x) * (denver_centroid[expect_part][0] - mid_x) > 0)}
    lat['denver_frame'] = {'transform': 'transforms/denver-aligned-ct-voxel-to-vhf.json', 'denver_frame_x_positive_is_subject_right': bool(denver_right_positive),
                           'denver_mesh_centroids_mm': {k: v.round(1).tolist() for k, v in denver_centroid.items()}, 'bones': rows, 'organs': organ_rows,
                           'ok': bool(rows) and bool(organ_rows) and all(r['same_side_as_denver_mesh'] for r in rows.values()) and all(r['ok'] for r in organ_rows.values())}
    print('denver frame laterality ok', lat['denver_frame']['ok'], 'x positive is right', denver_right_positive, flush=True)

lat['summary']['bone_side_mismatches'] = {m: v['mismatches'] for m, v in lat['bone_sides'].items()}
lat['summary']['ok'] = lat['summary']['organ_anchor_ok'] and not any(lat['summary']['bone_side_mismatches'].values()) and (VOX_TO_VHF is None or lat['denver_frame']['ok'])

summary = {c: sum(1 for b in bones.values() if b['consensus'] == c) for c in ['agree', 'partial', 'disagree', 'single']}
out = {'ct': CT, 'totalseg': str(TS.relative_to(ROOT)), 'moose': str(MOOSE.relative_to(ROOT)), 'skellytour': str(SKELLY.relative_to(ROOT)) if SKELLY.exists() else None,
       'shape': list(ts_arr.shape), 'affine_axcodes': list(nib.aff2axcodes(affine)), 'consensus_summary': summary, 'bones': bones,
       'vertebra_matching_diagnostic': vertebra_matching, 'laterality': lat,
       'note': 'agreement JSON only: consensus masks and uncertainty maps are produced per instance by scripts/ct-vertebra-instances.py; laterality checks are consistency checks that share TotalSegmentator organ labels'}
dest = ROOT / f'generated/ct-prior-consensus-{CT}.json'
dest.write_text(json.dumps(out, indent=1) + '\n')
print('summary', summary, 'laterality ok', lat['summary']['ok'], '->', dest.relative_to(ROOT))
