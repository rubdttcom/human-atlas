"""Convert the per-instance CT consensus label maps (three-model vote on the NLM VHF fresh CT) into viewer geometry.

Input : data/derived/nlm-vhf/consensus/{vertebra,rib-left,rib-right}-instances.nii.gz  (uint8 instance index per voxel,
        strict majority of the eligible models; scripts/ct-vertebra-instances.py nlm vertebrae|ribs_left|ribs_right)
        generated/ct-vertebra-instances-nlm.json, generated/ct-rib-instances-nlm-{left,right}.json (instance tables)
        transforms/nlm-ct-to-vhf.json (rigid same-donor pelvis registration CT -> VHF-image-2022)
Output: public/models/atlas-ct-consensus.json + ct-consensus-source-*.bin, generated/ct-consensus-qa.json

One mesh per consensus instance (marching cubes, step 1 voxel), placed like the NLM CT source (CT RAS mm ->
nlm-ct-to-vhf -> denver-image-to-stage). Ids are the geometric instance ids (V20, RL06, S29): no mesh carries an
anatomical name as its identity. The candidate name (HRA same-donor chain by order for vertebrae; the three
models' shared rib label for ribs) travels in the metadata with `name_status: pending`. Instances without
consensus (single-model pieces, the TotalSegmentator-only S1 body) are listed as review-only and not meshed.
Nothing is anatomically reviewed.

Usage: .venv/bin/python scripts/ingest-ct-consensus.py
"""
import hashlib
import json
import re
from pathlib import Path

import nibabel as nib
import numpy as np
import trimesh
from scipy import ndimage
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'public/models'
CONS = ROOT / 'data/derived/nlm-vhf/consensus'
FAMILIES = [('vertebrae', CONS / 'vertebra-instances.nii.gz', ROOT / 'generated/ct-vertebra-instances-nlm.json'),
            ('ribs_left', CONS / 'rib-left-instances.nii.gz', ROOT / 'generated/ct-rib-instances-nlm-left.json'),
            ('ribs_right', CONS / 'rib-right-instances.nii.gz', ROOT / 'generated/ct-rib-instances-nlm-right.json'),
            ('bones', CONS / 'bone-consensus.nii.gz', ROOT / 'generated/ct-bone-consensus-nlm.json')]   # per-name candidates, plan B 2.6; never composed


def bone_instances(report):
    """Normalise the per-name bone report (scripts/ct-bone-consensus.py) to the instance-table shape used below.
    Only `candidate-consensus` bones are meshed; the rest are listed as review-only candidates."""
    rows, review = [], []
    for cls, e in report['bones'].items():
        if e.get('status') == 'candidate-consensus':
            voted = {m: v['label'] for m, v in e['models'].items() if v['state'] == 'voted'}
            rows.append({'index': e['candidate_index'], 'id': f"B{e['candidate_index']:02d}", 'role': 'bone', 'bone_class': cls, 'kind': e['kind'],
                         'consensus_ml': e['consensus_ml'], 'union_ml': e['union_ml'], 'agreement_ratio': e['agreement_ratio'], 'unanimous_fraction': e['unanimous_fraction'],
                         'eligible_models_on_consensus': e['eligible_models_on_consensus'], 'votes_histogram_on_union': e['votes_histogram_on_union'], 'conflict_voxels': e['conflict_voxels'],
                         'lost_to_other_winner_ml': None, 'size_class': None, 'models': e['models'], 'source_labels': voted, 'name_status': 'pending',
                         'gates': e['gates'], 'consensus_status': e['status'], 'review_status': e['review_status'],
                         'versus_nlm_vhf_ct_label': e.get('versus_nlm_vhf_ct_label'), 'versus_denver_mesh': e.get('versus_denver_mesh'), 'denver_mesh': e.get('denver_mesh'),
                         'shape_check': e.get('shape_check')})
        elif e.get('status') not in (None, 'excluded'):
            review.append({'family': 'bones', 'id': cls, 'role': 'bone', 'status': e['status'], 'reasons': e.get('not_accepted_reasons'), 'models': {m: v['state'] for m, v in e.get('models', {}).items()},
                           'agreement_ratio': e.get('agreement_ratio'), 'unanimous_fraction': e.get('unanimous_fraction'), 'candidate_index': e.get('candidate_index'),
                           'reason': 'not a consensus candidate under plan B section 2.6; label map kept in data/derived (bone-single-model.nii.gz) or no mask'})
    return rows, review
ct_meta = json.loads((ROOT / 'data/derived/nlm-vhf/vhf-fresh-ct-metadata.json').read_text())
POSTURE_PATH = ROOT / 'generated/trunk-posture-offset.json'
POSTURE = json.loads(POSTURE_PATH.read_text())
POSTURE_SHA = hashlib.sha256(POSTURE_PATH.read_bytes()).hexdigest()
POSTURE_BY_ID = {**{lv['id']: lv for lv in POSTURE['levels']}, **{k: v for k, v in POSTURE['ribs'].items() if 'centroid_offset_vhf_mm' in v}}


def posture_offset(instance_id):
    """Plan B stage 0 measurement for this instance (scripts/trunk-posture-offset.py): Denver aligned CT minus NLM fresh CT
    in the canonical frame, posture + two registrations + two segmentations, not separated and not corrected."""
    lv = POSTURE_BY_ID.get(instance_id)
    if lv is None:
        return {'status': 'not-measured', 'report': str(POSTURE_PATH.relative_to(ROOT)), 'report_sha256': POSTURE_SHA}
    fit = lv['own_rigid_fit']
    return {'status': 'measured', 'report': str(POSTURE_PATH.relative_to(ROOT)), 'report_sha256': POSTURE_SHA, 'frame': POSTURE['frame'],
            'match': lv.get('match', 'same geometric id'), 'centroid_offset_vhf_mm': lv['centroid_offset_vhf_mm'],
            'surface_p95_placed_mm': lv['surface_distance_placed']['nlm_to_denver']['p95_mm'],
            'own_rigid_fit': {'angle_deg': fit['angle_deg'], 'about_x_right_deg': fit['about_x_right_deg'], 'about_y_anterior_deg': fit['about_y_anterior_deg'],
                              'about_z_superior_deg': fit['about_z_superior_deg'], 'residual_after_fit_p95_mm': fit['residual_after_fit']['nlm_to_denver']['p95_mm']},
            'relative_to_pelvis': lv.get('relative_to_pelvis'), 'common_shift_vhf_mm': POSTURE['summary']['common_shift_vhf_mm'],
            'discrepancy_threshold': lv.get('discrepancy_threshold'), 'registration_floor_pelvis_mm': POSTURE['summary']['registration_floor_pelvis_mm'],
            'whole_spine_chain_rotation_deg': POSTURE['summary']['whole_spine_chain_rotation_deg'],
            'note': 'Denver aligned CT (frozen block) minus NLM fresh CT (table) for the same consensus instance, each CT placed by its own rigid pelvis fit. '
                    'The figure mixes posture, two registration errors (translation and angle) and two segmentation differences; this calculation does not identify the cause of any part of it, '
                    'the pelvis-anchor offset included. Nothing is corrected, nothing is anatomy. Until a correction is recorded, this mesh is a prior with this measured discrepancy in the cryosection frame (plan B stage 0).'}
transform = json.loads((ROOT / 'transforms/nlm-ct-to-vhf.json').read_text())
stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
ts_labels = ROOT / 'data/derived/nlm-vhf/totalseg.nii'
assert transform['labels_sha256'] == hashlib.sha256(ts_labels.read_bytes()).hexdigest(), 'nlm-ct-to-vhf.json was fitted on another label map; re-run scripts/register-nlm-ct.py'
ts_im = nib.load(ts_labels)
ct_to_vhf = np.array(transform['matrix_row_major']).reshape(4, 4)
image_to_stage = np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4)
voxel_to_stage = image_to_stage @ ct_to_vhf @ ts_im.affine
voxel_mm3 = float(np.prod(ts_im.header.get_zooms()))

parts, concepts, chunks, reports, review_only = [], [], [], [], []
blob = bytearray()
input_hashes = {}


def append(values):
    while len(blob) % 4:
        blob.append(0)
    offset = len(blob)
    blob.extend(values.tobytes())
    return offset


def flush():
    if not blob:
        return
    name = f'ct-consensus-source-{len(chunks)}.bin'
    (OUT / name).write_bytes(blob)
    chunks.append({'url': '/models/' + name, 'bytes': len(blob)})
    blob.clear()


def candidate(inst, family):
    """Candidate anatomical name and its evidence; never the identity of the mesh."""
    if family == 'bones':
        g = inst['gates']
        pairs = g['geometric_correspondence']['pairs']
        return inst['bone_class'], (f"the {len(inst['source_labels'])} models name this bone alike ({inst['source_labels']}); gates of plan B 2.6 passed: class equivalence, "
                                    f"largest-component correspondence (IoU {min(p['iou_largest_components'] for p in pairs.values()):.2f} to {max(p['iou_largest_components'] for p in pairs.values()):.2f}, "
                                    f"centroid offsets <= {max(p['centroid_offset_mm'] for p in pairs.values()):.1f} mm), laterality {'checked' if g['laterality']['applicable'] else 'not applicable'}, "
                                    f"{g['coverage_eligibility']['eligible_models_on_union_majority']} eligible models; name agreement is not anatomical verification")
    if inst['role'] == 'sacrum':
        return 'sacrum', 'TotalSegmentator and MOOSE both label this instance sacrum; Skellytour has no sacrum class'
    if family == 'vertebrae':
        hn = inst.get('hra_name_by_order')
        if hn:
            return hn, ('HRA united-female v1.5 skeleton (modelled on the Visible Human Female, 25 vertebrae, six lumbar; NIH 3D 3DPX-020988) matched by order from the sacrum; '
                        f"z offset {inst.get('hra_z_offset_mm')} mm; the three models' own labels: {inst['source_labels']}")
        return None, 'no by-order name (counts differ or no consensus)'
    side = family.split('_')[1]
    numbers = set()
    for m, label in inst['source_labels'].items():
        match = re.search(r'(\d+)$', label)
        if match:
            numbers.add(int(match.group(1)))
    if len(numbers) == 1:
        return f'{side} rib {numbers.pop()}', f"the three models agree on the rib number: {inst['source_labels']}"
    return None, f"models disagree on the rib number: {inst['source_labels']}"


groups = {}
review_only_bones = []
for family, nii_path, table_path in FAMILIES:
    table = json.loads(table_path.read_text())
    if family == 'bones':
        rows, review_only_bones = bone_instances(table)
        table = {'instances': rows}
    image = nib.load(nii_path)
    assert image.shape == ts_im.shape and np.allclose(image.affine, ts_im.affine, atol=1e-3), f'{nii_path} is not on the NLM CT grid'
    volume = np.asarray(image.dataobj).astype(np.uint8)
    sha = hashlib.sha256(nii_path.read_bytes()).hexdigest()
    input_hashes[family] = {'instances_nii': str(nii_path.relative_to(ROOT)), 'sha256': sha, 'table': str(table_path.relative_to(ROOT))}
    boxes = ndimage.find_objects(volume)
    side = family.split('_')[1] if family.startswith('ribs') else None
    for inst in table['instances']:
        idx = inst['index']
        if inst['consensus_ml'] <= 0 or idx - 1 >= len(boxes) or boxes[idx - 1] is None:
            review_only.append({'family': family, 'id': inst['id'], 'role': inst['role'], 'size_class': inst.get('size_class'), 'union_ml': inst['union_ml'],
                                'models': {m: v['state'] for m, v in inst['models'].items()}, 'source_labels': inst['source_labels'],
                                'reason': 'no strict-majority consensus voxels; kept in the review map only'})
            continue
        box = boxes[idx - 1]
        mask = volume[box] == idx
        voxels = int(mask.sum())
        crop = np.pad(mask.astype(np.uint8), 1)
        vertices, faces, _, _ = marching_cubes(crop, .5, step_size=1, allow_degenerate=False)
        vertices += np.array([s.start for s in box]) - 1
        vertices = nib.affines.apply_affine(voxel_to_stage, vertices)
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        winding_reversed = bool(mesh.volume < 0)
        if winding_reversed:
            mesh.invert()
        components = mesh.split(only_watertight=False)
        pos = np.asarray(mesh.vertices, dtype='<f4')
        normal = np.asarray(np.clip(mesh.vertex_normals * 32767, -32767, 32767), dtype='<i2')
        indices = np.asarray(mesh.faces, dtype='<u4').ravel()
        if len(blob) > 6_000_000:
            flush()
        cand, evidence = candidate(inst, family)
        identity = f"CTCONS:VHF:{inst['id']}"
        if family == 'bones':
            laterality = 'left' if inst['bone_class'].endswith('_left') else 'right' if inst['bone_class'].endswith('_right') else 'midline'
            pretty = inst['bone_class'].replace('_left', '').replace('_right', '').replace('_', ' ')
            name = f"{laterality.capitalize() + ' ' if laterality != 'midline' else ''}{pretty} · consensus candidate {inst['id']} (machine-unverified)"
        elif inst['role'] == 'sacrum':
            name = f"Sacrum · consensus instance {inst['id']}"
            laterality = 'midline'
        elif family == 'vertebrae':
            name = f"Vertebra instance {inst['id']}" + (f' · candidate {cand}' if cand else '')
            laterality = 'midline'
        else:
            name = f"{side.capitalize()} rib instance {inst['id']}" + (f" · candidate rib {cand.split()[-1]}" if cand else '')
            laterality = side
        metadata = {'source_sex': 'female', 'source_donor': 'VHF', 'geometry_type': 'automatic_segmentation_consensus', 'input_sha256': ct_meta['sha256'],
                    'labels_sha256': sha, 'instance_family': family, 'instance_id': inst['id'], 'instance_index': idx, 'role': inst['role'], 'laterality': laterality,
                    'label_name': inst['source_labels'].get('totalseg', inst['id']) if family == 'bones' else inst['id'], 'lod_step_voxels': 1, 'voxel_count': voxels, 'volume_cm3': voxels * voxel_mm3 / 1000,
                    'consensus_ml': inst['consensus_ml'], 'union_ml': inst['union_ml'], 'agreement_ratio': inst['agreement_ratio'], 'unanimous_fraction': inst['unanimous_fraction'],
                    'conflict_voxels': inst['conflict_voxels'], 'lost_to_other_winner_ml': inst['lost_to_other_winner_ml'], 'size_class': inst.get('size_class'),
                    'eligible_models_on_consensus': inst['eligible_models_on_consensus'], 'votes_histogram_on_union': inst['votes_histogram_on_union'],
                    'models': inst['models'], 'source_labels': inst['source_labels'], 'fragments': inst.get('fragments'), 'seed_merged_from': inst.get('seed_merged_from'),
                    'candidate_name': cand, 'candidate_evidence': evidence, 'name_status': inst.get('name_status', 'pending'),
                    'hra_name_by_order': inst.get('hra_name_by_order'), 'hra_z_offset_mm': inst.get('hra_z_offset_mm'),
                    'crosses_skellytour_seam_z': inst.get('crosses_skellytour_seam_z'),
                    'posture_offset': posture_offset(inst['id']) if family != 'bones' else None,
                    'segmentation_models': 'TotalSegmentator 2.18.0 total (Apache-2.0); MOOSE 3.2.2 clin_ct_vertebrae / clin_ct_ribs (Apache-2.0 code, CC BY 4.0 weights); Skellytour high (Apache-2.0 code; weight licence to confirm, paper states CC BY 4.0)',
                    'vote_rule': 'one vote per model per geometric instance; strict majority of the eligible models per voxel (unsupported class, unprocessed region and absorbed-into-another-label kept apart from negative)',
                    'registration_transform': transform['id'], 'registration_p95_mm': transform['p95_mm'],
                    'ontology_mapping': ('shared label of the voting models resolved through the reviewed crosswalk of nlm-vhf-ct; machine-unverified' if family == 'bones'
                                         else 'none: geometric instance id; candidate anatomical name pending'),
                    'notes': ('Consensus of three open CT bone models on the NLM Visible Human Female fresh CT, voted per geometric instance so that a body every model names differently still gets one mask. '
                              'The id is geometric (cranial to caudal). The candidate name is evidence, not a decision: this donor has six lumbar-type vertebral bodies and the lumbosacral transition is an open question. '
                              'Placed in the canonical space by the same rigid same-donor pelvis registration as the NLM CT source. Not anatomically reviewed.')}
        if family == 'bones':
            metadata.update({'bone_class': inst['bone_class'], 'review_status': inst['review_status'], 'consensus_status': inst['consensus_status'], 'gates': inst['gates'],
                             'versus_nlm_vhf_ct_label': inst['versus_nlm_vhf_ct_label'], 'versus_denver_mesh': inst['versus_denver_mesh'], 'denver_mesh': inst['denver_mesh'],
                             'shape_check': inst['shape_check'],
                             'segmentation_models': 'TotalSegmentator 2.18.0 total (Apache-2.0); MOOSE 3.2.2 clin_ct_peripheral_bones / clin_ct_vertebrae / clin_ct_ribs (Apache-2.0 code, CC BY 4.0 weights); Skellytour high (Apache-2.0 code; weight licence to confirm, paper states CC BY 4.0)',
                             'vote_rule': 'one label per model per bone class (registry/ct-label-equivalence.json); gates of plan B 2.6 before the vote; strict majority of the eligible models per voxel (unsupported class, unprocessed region and absorbed-into-a-group-label kept apart from negative)',
                             'notes': ('Per-name consensus candidate of three open CT bone models on the NLM Visible Human Female fresh CT (plan B section 2.6). The models agree on the name and their largest components '
                                       'correspond; this is agreement between similar models on one CT, not anatomical verification. Machine-unverified: an alternative for comparison, never composed automatically; '
                                       'Denver measured geometry stays the atlas reference where it exists. Placed by the same rigid same-donor pelvis registration as the NLM CT source. '
                                       + ('Shape check of plan B 2.6 (rigid fit to the HU = 300 edge, same procedure as the Denver baseline): ' + inst['shape_check']['decision'] + '.' if inst.get('shape_check')
                                          else 'Shape check of plan B 2.6 not run: candidate pending the shape check, not an accepted atlas candidate.'))})
        part = {'id': identity, 'name': name, 'conceptId': identity, 'system': 'skeletal', 'chunk': len(chunks), 'positions': append(pos), 'normals': append(normal),
                'indices': append(indices), 'vertexCount': len(pos), 'indexCount': len(indices), 'bounds': [pos.min(axis=0).tolist(), pos.max(axis=0).tolist()], 'source_metadata': metadata}
        parts.append(part)
        concepts.append({'id': identity, 'name': name, 'elements': [identity]})
        if inst['role'] == 'vertebra':
            groups.setdefault('Vertebral column (consensus instances)', []).append(identity)
        elif inst['role'] == 'rib':
            groups.setdefault('Ribs (consensus instances)', []).append(identity)
            groups.setdefault(f'{side.capitalize()} ribs (consensus instances)', []).append(identity)
        elif inst['role'] == 'bone':
            groups.setdefault('Bones (consensus candidates, machine-unverified)', []).append(identity)
        reports.append({'family': family, 'instance': inst['id'], 'bone_class': inst.get('bone_class'), 'triangles': len(indices) // 3, 'vertices': len(pos), 'watertight': bool(mesh.is_watertight), 'components': len(components),
                        'winding_reversed': winding_reversed, 'volume_m3': float(mesh.volume), 'consensus_ml': inst['consensus_ml'], 'unanimous_fraction': inst['unanimous_fraction'],
                        'degenerate_faces': int(np.sum(mesh.area_faces < 1e-14)), 'self_intersections': 'not-assessed', 'anatomical_review': 'pending', 'name_status': 'pending'})
        print(f"{family} {inst['id']}: {len(indices)//3} triangles, {len(components)} components, candidate {cand}", flush=True)
flush()
for key, elements in groups.items():
    if len(elements) > 1:
        concepts.append({'id': f'CTCONS:VHF:group:{key}', 'name': key, 'elements': elements})
atlas = {'version': 'NLM Visible Human Female fresh CT, three-model consensus by geometric instance (vertebrae, ribs) and gated per-name bone candidates', 'sex': 'female', 'source': 'CT consensus instances (VHF)',
         'scope': 'Female donor VHF: vertebrae, sacrum and ribs voted per geometric instance from TotalSegmentator, MOOSE and Skellytour on the NLM fresh CT (ids geometric, names pending), plus per-name bone candidates that passed the gates of plan B 2.6 (machine-unverified, never composed automatically); same rigid same-donor registration as the NLM CT source; unreviewed',
         'parts': parts, 'concepts': concepts, 'chunks': chunks, 'triangles': sum(p['indexCount'] // 3 for p in parts),
         'input_sha256': ct_meta['sha256'], 'labels_sha256': transform['labels_sha256'], 'instance_maps': input_hashes, 'ct_metadata': 'data/derived/nlm-vhf/vhf-fresh-ct-metadata.json',
         'source_affine': ts_im.affine.tolist(), 'voxel_to_stage': voxel_to_stage.tolist(), 'ct_to_vhf': transform, 'voxel_spacing_mm': [float(v) for v in ts_im.header.get_zooms()],
         'review_only_instances': review_only, 'review_only_bone_candidates': review_only_bones,
         'licence_evidence': {'input': 'NLM Terms and Conditions (no licence since July 2019; attribution "Courtesy of the U.S. National Library of Medicine")',
                              'models': ['TotalSegmentator task total: Apache-2.0', 'MOOSE 3.2.2: Apache-2.0 code, CC BY 4.0 weights', 'Skellytour: Apache-2.0 code; weight licence to confirm (paper states CC BY 4.0)']},
         'citation': ['Wasserthal et al. 2023, https://doi.org/10.1148/ryai.230024', 'MOOSE, https://github.com/ENHANCE-PET/MOOSE', 'Skellytour, Wardell et al. 2025, Radiology: Artificial Intelligence',
                      'HRA united-female v1.5, https://lod.humanatlas.io/ref-organ/united-female/v1.5', 'NIH 3D 3DPX-020988, https://3d.nih.gov/entries/3DPX-020988',
                      'NLM Visible Human Project, https://www.nlm.nih.gov/research/visible/visible_human.html']}
(OUT / 'atlas-ct-consensus.json').write_text(json.dumps(atlas, separators=(',', ':')))
(ROOT / 'generated/ct-consensus-qa.json').write_text(json.dumps({'meshes': reports, 'review_only_instances': review_only, 'review_only_bone_candidates': review_only_bones}, indent=2) + '\n')
print(json.dumps({'meshes': len(parts), 'triangles': atlas['triangles'], 'review_only': len(review_only), 'chunks': len(chunks)}))
