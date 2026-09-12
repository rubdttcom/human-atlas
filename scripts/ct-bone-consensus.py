"""Per-name bone consensus on the VHF donor CT, gated (plan B section 2.6): name agreement is the start, not the proof.

Usage: .venv/bin/python scripts/ct-bone-consensus.py nlm [--no-denver]
       .venv/bin/python scripts/ct-bone-consensus.py --selftest

For every class of registry/ct-label-equivalence.json except vertebrae, ribs and the sacrum (instance consensus),
the three models' labels pass four gates before any vote, and the result is a CANDIDATE, never a substitution:
  1. class equivalence     the registry maps the labels; group labels never meet individual bones;
  2. geometric correspondence   largest connected component per model: every pair IoU >= 0.50 and centroid <= 15 mm,
                           else `disputed` (no consensus mask; per-model masks stay as alternatives); smaller
                           components are listed as fragments;
  3. laterality            *_left centroid x < 0 and *_right x > 0 in RAS (+x subject right, anchored by the
                           organ test of ct-prior-consensus.py, whose result is read, not recomputed); a mismatch
                           in any model fails both sides of the pair;
  4. coverage and eligibility   a model is eligible where it processed the region (Skellytour body crop) and has
                           the class; fewer than two eligible models => `single-model` candidate. Bones whose union
                           have at least 2 % of their surface voxels in contact with the CT field-of-view edge (coverage mask) are flagged `truncated` (contact fraction and mL always recorded; outside the FOV the models predict nothing, so the missing part is never in the union).
Vote: strict majority of the eligible models per voxel, with the same figures as the instance tables
(consensus_ml, union_ml, agreement_ratio = consensus/union, unanimous_fraction over consensus voxels, histograms,
conflict_voxels = union voxels where a model carries another bone class of the registry). Acceptance as an atlas
candidate (section 2.6): gates passed, agreement_ratio >= 0.70, unanimous_fraction >= 0.60, not truncated; the
geometry and shape checks happen at ingestion. Comparison, never substitution: Dice and volume ratio against the
current TotalSegmentator label (source nlm-vhf-ct) and, where a Denver mesh exists, the distance from the
candidate's surface voxels (CT -> nlm-ct-to-vhf -> stage) to the Denver mesh vertices (p50/p95, mm) and back.

Outputs: generated/ct-bone-consensus-<ct>.json,
         data/derived/<ct dir>/consensus/bone-consensus.nii.gz   (uint8 class index; only bones with >= 2 eligible models)
         data/derived/<ct dir>/consensus/bone-single-model.nii.gz (uint8 class index; single-model candidates)
Nothing here is anatomically reviewed; every output is machine-unverified.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
IOU_MIN, CENTROID_MAX_MM = 0.50, 15.0
ACCEPT_AGREEMENT, ACCEPT_UNANIMOUS = 0.70, 0.60
TRUNCATED_MIN_FRACTION = 0.02   # fraction of the union's surface voxels in contact with the CT field-of-view edge that marks a bone as truncated (always recorded)
SKIP = {'sacrum'}


def largest_component(mask):
    lab, n = ndimage.label(mask)
    if n == 0:
        return mask, []
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    k = int(np.argmax(sizes)) + 1
    frags = [{'voxels': int(s)} for i, s in enumerate(sizes, start=1) if i != k]
    return lab == k, frags


def centroid_world(mask, box, affine):
    c = np.array(ndimage.center_of_mass(mask)) + np.array([s.start for s in box])
    return (affine @ np.r_[c, 1])[:3]


def union_box(boxes, shape, pad=2):
    return tuple(slice(max(0, min(b[d].start for b in boxes) - pad), min(shape[d], max(b[d].stop for b in boxes) + pad)) for d in range(3))


def gate_geometry(masks, affine, box):
    """masks: {model: bool array on box}. Largest components, pairwise IoU and centroid distance."""
    main, frags, cent = {}, {}, {}
    for m, a in masks.items():
        main[m], frags[m] = largest_component(a)
        cent[m] = centroid_world(main[m], box, affine)
    pairs, ok = {}, True
    names = list(masks)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = main[names[i]], main[names[j]]
            inter, uni = int((a & b).sum()), int((a | b).sum())
            iou = inter / uni if uni else 0.0
            d = float(np.linalg.norm(cent[names[i]] - cent[names[j]]))
            passed = iou >= IOU_MIN and d <= CENTROID_MAX_MM
            pairs[f'{names[i]}|{names[j]}'] = {'iou_largest_components': round(iou, 4), 'centroid_offset_mm': round(d, 2), 'passed': passed}
            ok &= passed
    return main, frags, cent, pairs, ok


def gate_laterality(cls, cent):
    side = 'left' if cls.endswith('_left') else 'right' if cls.endswith('_right') else None
    if side is None:
        return {'applicable': False, 'passed': True}
    per = {m: ('left' if c[0] < 0 else 'right') for m, c in cent.items()}
    return {'applicable': True, 'expected': side, 'per_model_side': per, 'passed': all(v == side for v in per.values())}


def vote(masks, eligible, vox_ml, other_class_masks):
    """masks: {model: bool} of the class; eligible: {model: bool} where the model could vote; other_class_masks: {model: bool} where the
    model carries another bone class of the registry. Returns the consensus mask and the instance-table figures."""
    models = list(masks)
    votes = sum(masks[m].astype(np.uint8) for m in models)
    elig = sum(eligible[m].astype(np.uint8) for m in models)
    union = votes > 0
    cons = (votes * 2 > elig) & union
    n_c, n_u = int(cons.sum()), int(union.sum())
    other = sum(other_class_masks[m].astype(np.uint8) for m in models) > 0
    fig = {'consensus_ml': round(n_c * vox_ml, 2), 'union_ml': round(n_u * vox_ml, 2),
           'agreement_ratio': round(n_c / n_u, 3) if n_u else None,
           'unanimous_fraction': round(float((votes[cons] == elig[cons]).mean()), 3) if n_c else None,
           'eligible_models_on_consensus': {str(int(e)): int((elig[cons] == e).sum()) for e in np.unique(elig[cons])} if n_c else {},
           'votes_histogram_on_union': {str(int(v)): int((votes[union] == v).sum()) for v in np.unique(votes[union])} if n_u else {},
           'conflict_voxels': int((union & other).sum())}
    return cons, fig


def selftest():
    """Synthetic 3-model grids: agree, disputed (shifted), laterality swap, single-model, group excluded."""
    shape = (60, 40, 40)
    affine = np.diag([1.0, 1.0, 1.0, 1.0]); affine[0, 3] = -30   # x from -30 to +29: negative = left
    def box(x0, x1, y0, y1, z0, z1):
        a = np.zeros(shape, bool); a[x0:x1, y0:y1, z0:z1] = True; return a
    left = box(5, 15, 10, 20, 10, 20)
    shifted = box(5, 15, 10, 20, 24, 34)          # no overlap with `left`
    right_wrong = box(5, 15, 25, 35, 10, 20)      # a *_right label sitting at x < 0
    full = tuple(slice(0, s) for s in shape)
    el = {m: np.ones(shape, bool) for m in ('a', 'b', 'c')}
    none = {m: np.zeros(shape, bool) for m in ('a', 'b', 'c')}
    main, frags, cent, pairs, ok = gate_geometry({'a': left, 'b': left, 'c': left}, affine, full)
    assert ok and all(p['iou_largest_components'] == 1.0 for p in pairs.values())
    cons, fig = vote({'a': left, 'b': left, 'c': left}, el, 0.001, none)
    assert fig['agreement_ratio'] == 1.0 and fig['unanimous_fraction'] == 1.0 and fig['votes_histogram_on_union'] == {'3': 1000} and fig['conflict_voxels'] == 0
    _, _, _, pairs, ok = gate_geometry({'a': left, 'b': left, 'c': shifted}, affine, full)
    assert not ok and pairs['a|c']['iou_largest_components'] == 0.0 and pairs['a|b']['passed']
    lat = gate_laterality('femur_right', {'a': cent['a']})
    assert lat['applicable'] and not lat['passed'] and lat['per_model_side']['a'] == 'left'
    assert gate_laterality('femur_left', {'a': cent['a']})['passed'] and not gate_laterality('skull', {})['applicable']
    # partial agreement: two models vote a box, the third votes half of it => consensus = full box, unanimous 0.5
    half = box(5, 15, 10, 20, 10, 15)
    cons, fig = vote({'a': left, 'b': left, 'c': half}, el, 0.001, none)
    assert fig['consensus_ml'] == 1.0 and fig['unanimous_fraction'] == 0.5 and fig['votes_histogram_on_union'] == {'2': 500, '3': 500}
    # one model ineligible in half the box: that half has 2 eligible models; a single vote there is not a strict majority
    el2 = {'a': np.ones(shape, bool), 'b': np.ones(shape, bool), 'c': box(0, 60, 0, 40, 0, 15)}
    cons, fig = vote({'a': left, 'b': np.zeros(shape, bool), 'c': half}, el2, 0.001, none)
    assert fig['consensus_ml'] == 0.5 and fig['agreement_ratio'] == 0.5, fig
    # conflict: model b labels part of the union as another class
    cons, fig = vote({'a': left, 'b': left, 'c': left}, el, 0.001, {'a': none['a'], 'b': half, 'c': none['c']})
    assert fig['conflict_voxels'] == 500
    # laterality swap on a right label, largest component with fragments
    frag = left | box(30, 33, 10, 13, 10, 13)
    main, frags, _, _, _ = gate_geometry({'a': frag}, affine, full)
    assert frags['a'] == [{'voxels': 27}] and int(main['a'].sum()) == 1000
    print(json.dumps({'selftest': 'ok', 'cases': ['agree', 'disputed', 'laterality', 'partial', 'eligibility', 'conflict', 'fragments']}))


def main():
    if '--selftest' in sys.argv:
        return selftest()
    import nibabel as nib
    ct = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'nlm'
    if ct != 'nlm':
        sys.exit('only the NLM fresh CT is wired for the per-name batch today (the Denver aligned CT lacks the coverage mask and the stage transform used here)')
    TS = ROOT / 'data/derived/nlm-vhf/totalseg.nii'
    MOOSE = ROOT / 'data/derived/nlm-vhf/moose/segmentations'
    SKELLY = ROOT / 'data/derived/nlm-vhf/skellytour/skellytour_high.nii.gz'
    COVER = ROOT / 'data/derived/nlm-vhf/ct-coverage-mask.nii.gz'
    OUTDIR = ROOT / 'data/derived/nlm-vhf/consensus'
    registry = json.loads((ROOT / 'registry/ct-label-equivalence.json').read_text())
    prior = json.loads((ROOT / 'generated/ct-prior-consensus-nlm.json').read_text())
    lat_summary = prior['laterality']['summary']
    ts_im = nib.load(TS)
    affine = ts_im.affine
    shape = ts_im.shape
    vox_ml = float(np.prod(np.abs(np.diag(affine)[:3])) / 1000)
    print('loading label volumes', flush=True)
    arrays = {'totalseg': np.asanyarray(ts_im.dataobj).astype(np.uint8)}
    ids = {'totalseg': {v: int(k) for k, v in json.loads((ROOT / 'data/derived/nlm-vhf/totalseg-classmap.json').read_text())['total'].items()}}
    for task in ('peripheral_bones', 'vertebrae', 'ribs'):
        im = nib.load(MOOSE / f'clin_CT_{task}_segmentation_CT_vhf.nii.gz')
        assert im.shape == shape and np.allclose(im.affine, affine, atol=1e-3), task
        arrays[f'moose:{task}'] = np.asanyarray(im.dataobj).astype(np.uint8)
        ids[f'moose:{task}'] = {v['name']: int(k) for k, v in json.loads((MOOSE / f'clin_CT_{task}_organ_indices.json').read_text())['organ_indices'].items()}
    sk_im = nib.load(SKELLY)
    assert sk_im.shape == shape and np.allclose(sk_im.affine, affine, atol=1e-3)
    arrays['skellytour'] = np.asanyarray(sk_im.dataobj).astype(np.uint8)
    sk_labels = {'SKULL': 1, 'PELVIS': 2, 'STERNUM': 3, 'LEFT_FEMUR': 4, 'RIGHT_FEMUR': 5, 'LEFT_HUMERUS': 6, 'RIGHT_HUMERUS': 7, 'LEFT_SCAPULA': 8, 'RIGHT_SCAPULA': 9, 'LEFT_CLAVICLE': 10, 'RIGHT_CLAVICLE': 11}
    ids['skellytour'] = sk_labels
    plan = json.loads((SKELLY.parent / 'plan.json').read_text())
    i0, i1, j0, j1 = plan['crop']
    sk_processed = np.zeros(shape, bool); sk_processed[i0:i1, j0:j1, :] = True
    cover_im = nib.load(COVER)
    assert cover_im.shape == shape
    coverage = np.asanyarray(cover_im.dataobj) > 0
    input_sha = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [TS, SKELLY, COVER] + [MOOSE / f'clin_CT_{t}_segmentation_CT_vhf.nii.gz' for t in ('peripheral_bones', 'vertebrae', 'ribs')]}
    print('volumes ready', flush=True)

    # bone-class masks per model for the conflict count: every registry label of that model
    def model_key(model, spec):
        return f'moose:{spec[0]}' if model == 'moose' else model
    class_labels = {}   # model array key -> set of label ids that are registry bone classes
    for e in registry['classes']:
        for model, spec in e['labels'].items():
            if spec is None:
                continue
            key = model_key(model, spec)
            lab = spec[1] if model == 'moose' else spec
            if lab in ids[key]:
                class_labels.setdefault(key, set()).add(ids[key][lab])

    # stage transform and Denver meshes for the comparison
    denver = {}
    if '--no-denver' not in sys.argv:
        transform = json.loads((ROOT / 'transforms/nlm-ct-to-vhf.json').read_text())
        stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
        voxel_to_stage = np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4) @ np.array(transform['matrix_row_major']).reshape(4, 4) @ affine
        atlas = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
        buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in atlas['chunks']]
        for part in atlas['parts']:
            v = np.frombuffer(buffers[part['chunk']], '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3).astype(np.float64)
            denver[part['id']] = v
    else:
        voxel_to_stage = None

    def surface_points(mask, box):
        er = ndimage.binary_erosion(mask)
        idx = np.argwhere(mask & ~er) + np.array([s.start for s in box])
        pts = (voxel_to_stage @ np.c_[idx, np.ones(len(idx))].T).T[:, :3]
        return pts

    consensus_map = np.zeros(shape, np.uint8)
    single_map = np.zeros(shape, np.uint8)
    report = {'ct': 'nlm', 'inputs_sha256': input_sha, 'registry': 'registry/ct-label-equivalence.json', 'thresholds': {'iou_min': IOU_MIN, 'centroid_max_mm': CENTROID_MAX_MM, 'accept_agreement_ratio': ACCEPT_AGREEMENT, 'accept_unanimous_fraction': ACCEPT_UNANIMOUS},
              'laterality_anchor': lat_summary, 'vote_rule': 'one label per model per class; strict majority of the eligible models per voxel; unsupported (no class), unprocessed (outside the Skellytour crop) and absorbed (group label PELVIS) kept apart from negative',
              'status_vocabulary': 'candidate-consensus | candidate-single-model | disputed | laterality-failed | not-accepted (metrics below floor or truncated) | excluded (instance consensus)', 'bones': {}}
    index = 0
    for e in registry['classes']:
        cls = e['class']
        if cls in SKIP:
            report['bones'][cls] = {'status': 'excluded', 'reason': e.get('note')}
            continue
        # gate 1: which models have an equivalent label
        avail, states = {}, {}
        for model, spec in e['labels'].items():
            if spec is None:
                states[model] = {'state': 'unsupported'}
                continue
            key = model_key(model, spec)
            lab = spec[1] if model == 'moose' else spec
            if lab not in ids[key]:
                states[model] = {'state': 'unsupported'}
                continue
            avail[model] = (key, ids[key][lab], lab)
        boxes = {}
        for model, (key, lid, lab) in avail.items():
            objs = ndimage.find_objects(arrays[key] == lid, max_label=1)
            if objs and objs[0] is not None:
                boxes[model] = objs[0]
            else:
                states[model] = {'state': 'negative', 'label': lab}
        present = {m: avail[m] for m in boxes}
        if not present:
            report['bones'][cls] = {'status': 'not-found', 'models': states}
            continue
        box = union_box(list(boxes.values()), shape)
        masks = {m: arrays[key][box] == lid for m, (key, lid, lab) in present.items()}
        eligible = {}
        for model in e['labels']:
            if model not in avail:
                eligible[model] = np.zeros(masks[next(iter(masks))].shape, bool)
            elif model == 'skellytour':
                eligible[model] = sk_processed[box]
            else:
                eligible[model] = np.ones(masks[next(iter(masks))].shape, bool)
        # Skellytour without an individual class but with PELVIS covering the union: absorbed, not negative
        if e['labels']['skellytour'] is None and 'skellytour' in states and states['skellytour']['state'] == 'unsupported':
            uni = np.zeros(masks[next(iter(masks))].shape, bool)
            for a in masks.values():
                uni |= a
            pel = (arrays['skellytour'][box] == sk_labels['PELVIS']) & uni
            if uni.any() and pel.sum() / uni.sum() >= 0.5:
                states['skellytour'] = {'state': 'absorbed', 'absorbed_into': 'PELVIS', 'fraction_of_union': round(float(pel.sum() / uni.sum()), 3)}
        for model in list(states):
            if states[model]['state'] == 'negative' and model == 'skellytour':
                uni = np.zeros(masks[next(iter(masks))].shape, bool)
                for a in masks.values():
                    uni |= a
                frac = float(sk_processed[box][uni].mean()) if uni.any() else 0.0
                if frac < 0.5:
                    states[model] = {'state': 'unprocessed', 'processed_fraction': round(frac, 3)}
        main, frags, cent, pairs, geom_ok = gate_geometry(masks, affine, box)
        for m, (key, lid, lab) in present.items():
            n = int(masks[m].sum())
            states[m] = {'state': 'voted', 'label': lab, 'candidate_ml': round(n * vox_ml, 2), 'largest_component_ml': round(int(main[m].sum()) * vox_ml, 2), 'fragments': len(frags[m]),
                         'fragments_ml': round(sum(f['voxels'] for f in frags[m]) * vox_ml, 2), 'centroid_ras_mm': [round(float(x), 1) for x in cent[m]]}
        lat = gate_laterality(cls, cent)
        # gate 4: eligibility count over the union, coverage
        uni = np.zeros(masks[next(iter(masks))].shape, bool)
        for a in masks.values():
            uni |= a
        n_elig = sum(eligible[m][uni].mean() >= 0.5 for m in eligible)
        # Field-of-view truncation. Outside the acquired FOV the CT holds padding and the models predict nothing, so the
        # union can never contain the missing part: measure the contact of the union with the FOV edge instead (union
        # voxels within one voxel of a non-covered voxel), as a fraction of the union's surface voxels.
        outside_fraction = float((~coverage[box])[uni].mean()) if uni.any() else 0.0
        edge = ndimage.binary_dilation(~coverage[box], iterations=1) & uni
        surface = uni & ~ndimage.binary_erosion(uni)
        contact_fraction = float(edge.sum() / surface.sum()) if surface.any() else 0.0
        truncated = contact_fraction
        # per-voxel eligibility must reflect class support too: models without the class are never eligible (zeros above)
        other = {}
        for model in e['labels']:
            if model not in avail:
                other[model] = np.zeros(uni.shape, bool)
                continue
            key, lid, lab = avail[model]
            labs = class_labels.get(key, set()) - {lid}
            other[model] = np.isin(arrays[key][box], list(labs)) if labs else np.zeros(uni.shape, bool)
        vote_masks = {m: masks.get(m, np.zeros(uni.shape, bool)) for m in e['labels'] if m in avail}
        vote_elig = {m: eligible[m] for m in vote_masks}
        cons, fig = vote(vote_masks, vote_elig, vox_ml, {m: other[m] for m in vote_masks})
        entry = {'kind': e['kind'], 'models': states, 'gates': {'class_equivalence': {'equivalent_models': sorted(avail), 'passed': True},
                 'geometric_correspondence': {'pairs': pairs, 'passed': geom_ok}, 'laterality': lat,
                 'coverage_eligibility': {'eligible_models_on_union_majority': int(n_elig), 'fov_edge_contact_fraction_of_surface': round(contact_fraction, 4), 'fov_edge_contact_ml': round(int(edge.sum()) * vox_ml, 2),
                                          'union_outside_coverage_fraction': round(outside_fraction, 4), 'truncated': contact_fraction >= TRUNCATED_MIN_FRACTION}},
                 **fig, 'denver_mesh': e.get('denver_mesh')}
        # status
        if not lat['passed']:
            status = 'laterality-failed'
        elif len(present) >= 2 and not geom_ok:
            status = 'disputed'
        elif n_elig < 2 or len(present) < 2:
            status = 'candidate-single-model'
        elif fig['agreement_ratio'] is not None and fig['agreement_ratio'] >= ACCEPT_AGREEMENT and fig['unanimous_fraction'] >= ACCEPT_UNANIMOUS and not entry['gates']['coverage_eligibility']['truncated']:
            status = 'candidate-consensus'
        else:
            status = 'not-accepted'
            reasons = []
            if fig['agreement_ratio'] is None or fig['agreement_ratio'] < ACCEPT_AGREEMENT:
                reasons.append(f"agreement_ratio {fig['agreement_ratio']} below {ACCEPT_AGREEMENT}")
            if fig['unanimous_fraction'] is None or fig['unanimous_fraction'] < ACCEPT_UNANIMOUS:
                reasons.append(f"unanimous_fraction {fig['unanimous_fraction']} below {ACCEPT_UNANIMOUS}")
            if entry['gates']['coverage_eligibility']['truncated']:
                reasons.append(f"{contact_fraction:.1%} of the surface touches the CT field-of-view edge (>= {TRUNCATED_MIN_FRACTION:.0%}): the bone is cut by the acquisition; only the cryosections can complete it")
            entry['not_accepted_reasons'] = reasons
        entry['status'] = status
        entry['review_status'] = 'machine-unverified'
        if status == 'candidate-single-model':
            # one model cannot agree with itself: the vote figures are undefined, not perfect
            for key in ('agreement_ratio', 'unanimous_fraction'):
                entry[key] = None
            entry['eligible_models_on_consensus'] = {}
            entry['agreement_note'] = 'single model: no agreement is measurable; consensus_ml is that model\'s label volume'
        # candidate mask: consensus when >= 2 eligible models voted, else the single model's largest component + fragments (its full label)
        if status in ('candidate-consensus', 'not-accepted') and len(present) >= 2:
            cand = cons
        elif status == 'candidate-single-model':
            cand = masks[next(iter(present))]
        else:
            cand = None
        if cand is not None and cand.any():
            index += 1
            entry['candidate_index'] = index
            target = consensus_map if len(present) >= 2 else single_map
            sub = target[box]
            sub[cand & (sub == 0)] = index
            # comparison with the current source (TotalSegmentator label = nlm-vhf-ct) and Denver
            if 'totalseg' in masks:
                ts = masks['totalseg']
                inter = int((ts & cand).sum())
                entry['versus_nlm_vhf_ct_label'] = {'dice': round(2 * inter / (int(ts.sum()) + int(cand.sum())), 4), 'volume_ratio_candidate_over_label': round(float(cand.sum() / ts.sum()), 4)}
            if e.get('denver_mesh') and e['denver_mesh'] in denver:
                pts = surface_points(cand, box)
                verts = denver[e['denver_mesh']]
                d1 = cKDTree(verts).query(pts, workers=-1)[0] * 1000
                d2 = cKDTree(pts).query(verts, workers=-1)[0] * 1000
                entry['versus_denver_mesh'] = {'mesh': e['denver_mesh'], 'candidate_surface_to_denver_vertices_mm': {'p50': round(float(np.percentile(d1, 50)), 2), 'p95': round(float(np.percentile(d1, 95)), 2)},
                                              'denver_vertices_to_candidate_surface_mm': {'p50': round(float(np.percentile(d2, 50)), 2), 'p95': round(float(np.percentile(d2, 95)), 2)},
                                              'note': 'vertex-to-surface-voxel distances in the canonical stage under nlm-ct-to-vhf; posture and registration error included; a comparison, not a substitution decision'}
        report['bones'][cls] = entry
        print(f"{cls:18s} {status:24s} agree {fig['agreement_ratio']} unanimous {fig['unanimous_fraction']} models {len(present)} elig {n_elig}" + (f" fov-edge {contact_fraction:.3f}" if contact_fraction > 0 else ''), flush=True)
    import nibabel as nib2
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for name, arr in (('bone-consensus.nii.gz', consensus_map), ('bone-single-model.nii.gz', single_map)):
        nib2.save(nib2.Nifti1Image(arr, affine), OUTDIR / name)
    report['outputs'] = {name: {'path': str((OUTDIR / name).relative_to(ROOT)), 'sha256': hashlib.sha256((OUTDIR / name).read_bytes()).hexdigest()} for name in ('bone-consensus.nii.gz', 'bone-single-model.nii.gz')}
    report['candidate_index'] = {v['candidate_index']: k for k, v in report['bones'].items() if 'candidate_index' in v}
    counts = {}
    for v in report['bones'].values():
        counts[v['status']] = counts.get(v['status'], 0) + 1
    report['summary'] = counts
    (ROOT / 'generated/ct-bone-consensus-nlm.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
