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
            ('ribs_right', CONS / 'rib-right-instances.nii.gz', ROOT / 'generated/ct-rib-instances-nlm-right.json')]
ct_meta = json.loads((ROOT / 'data/derived/nlm-vhf/vhf-fresh-ct-metadata.json').read_text())
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
for family, nii_path, table_path in FAMILIES:
    table = json.loads(table_path.read_text())
    image = nib.load(nii_path)
    assert image.shape == ts_im.shape and np.allclose(image.affine, ts_im.affine, atol=1e-3), f'{nii_path} is not on the NLM CT grid'
    volume = np.asarray(image.dataobj).astype(np.uint8)
    sha = hashlib.sha256(nii_path.read_bytes()).hexdigest()
    input_hashes[family] = {'instances_nii': str(nii_path.relative_to(ROOT)), 'sha256': sha, 'table': str(table_path.relative_to(ROOT))}
    boxes = ndimage.find_objects(volume)
    side = family.split('_')[1] if family != 'vertebrae' else None
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
        if inst['role'] == 'sacrum':
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
                    'label_name': inst['id'], 'lod_step_voxels': 1, 'voxel_count': voxels, 'volume_cm3': voxels * voxel_mm3 / 1000,
                    'consensus_ml': inst['consensus_ml'], 'union_ml': inst['union_ml'], 'agreement_ratio': inst['agreement_ratio'], 'unanimous_fraction': inst['unanimous_fraction'],
                    'conflict_voxels': inst['conflict_voxels'], 'lost_to_other_winner_ml': inst['lost_to_other_winner_ml'], 'size_class': inst.get('size_class'),
                    'eligible_models_on_consensus': inst['eligible_models_on_consensus'], 'votes_histogram_on_union': inst['votes_histogram_on_union'],
                    'models': inst['models'], 'source_labels': inst['source_labels'], 'fragments': inst.get('fragments'), 'seed_merged_from': inst.get('seed_merged_from'),
                    'candidate_name': cand, 'candidate_evidence': evidence, 'name_status': inst.get('name_status', 'pending'),
                    'hra_name_by_order': inst.get('hra_name_by_order'), 'hra_z_offset_mm': inst.get('hra_z_offset_mm'),
                    'crosses_skellytour_seam_z': inst.get('crosses_skellytour_seam_z'),
                    'segmentation_models': 'TotalSegmentator 2.18.0 total (Apache-2.0); MOOSE 3.2.2 clin_ct_vertebrae / clin_ct_ribs (Apache-2.0 code, CC BY 4.0 weights); Skellytour high (Apache-2.0 code; weight licence to confirm, paper states CC BY 4.0)',
                    'vote_rule': 'one vote per model per geometric instance; strict majority of the eligible models per voxel (unsupported class, unprocessed region and absorbed-into-another-label kept apart from negative)',
                    'registration_transform': transform['id'], 'registration_p95_mm': transform['p95_mm'],
                    'ontology_mapping': 'none: geometric instance id; candidate anatomical name pending',
                    'notes': ('Consensus of three open CT bone models on the NLM Visible Human Female fresh CT, voted per geometric instance so that a body every model names differently still gets one mask. '
                              'The id is geometric (cranial to caudal). The candidate name is evidence, not a decision: this donor has six lumbar-type vertebral bodies and the lumbosacral transition is an open question. '
                              'Placed in the canonical space by the same rigid same-donor pelvis registration as the NLM CT source. Not anatomically reviewed.')}
        part = {'id': identity, 'name': name, 'conceptId': identity, 'system': 'skeletal', 'chunk': len(chunks), 'positions': append(pos), 'normals': append(normal),
                'indices': append(indices), 'vertexCount': len(pos), 'indexCount': len(indices), 'bounds': [pos.min(axis=0).tolist(), pos.max(axis=0).tolist()], 'source_metadata': metadata}
        parts.append(part)
        concepts.append({'id': identity, 'name': name, 'elements': [identity]})
        if inst['role'] == 'vertebra':
            groups.setdefault('Vertebral column (consensus instances)', []).append(identity)
        elif inst['role'] == 'rib':
            groups.setdefault('Ribs (consensus instances)', []).append(identity)
            groups.setdefault(f'{side.capitalize()} ribs (consensus instances)', []).append(identity)
        reports.append({'family': family, 'instance': inst['id'], 'triangles': len(indices) // 3, 'vertices': len(pos), 'watertight': bool(mesh.is_watertight), 'components': len(components),
                        'winding_reversed': winding_reversed, 'volume_m3': float(mesh.volume), 'consensus_ml': inst['consensus_ml'], 'unanimous_fraction': inst['unanimous_fraction'],
                        'degenerate_faces': int(np.sum(mesh.area_faces < 1e-14)), 'self_intersections': 'not-assessed', 'anatomical_review': 'pending', 'name_status': 'pending'})
        print(f"{family} {inst['id']}: {len(indices)//3} triangles, {len(components)} components, candidate {cand}", flush=True)
flush()
for key, elements in groups.items():
    if len(elements) > 1:
        concepts.append({'id': f'CTCONS:VHF:group:{key}', 'name': key, 'elements': elements})
atlas = {'version': 'NLM Visible Human Female fresh CT, three-model consensus by geometric instance (vertebrae, ribs)', 'sex': 'female', 'source': 'CT consensus instances (VHF)',
         'scope': 'Female donor VHF: vertebrae, sacrum and ribs voted per geometric instance from TotalSegmentator, MOOSE and Skellytour on the NLM fresh CT; ids are geometric, names pending; same rigid same-donor registration as the NLM CT source; unreviewed',
         'parts': parts, 'concepts': concepts, 'chunks': chunks, 'triangles': sum(p['indexCount'] // 3 for p in parts),
         'input_sha256': ct_meta['sha256'], 'labels_sha256': transform['labels_sha256'], 'instance_maps': input_hashes, 'ct_metadata': 'data/derived/nlm-vhf/vhf-fresh-ct-metadata.json',
         'source_affine': ts_im.affine.tolist(), 'voxel_to_stage': voxel_to_stage.tolist(), 'ct_to_vhf': transform, 'voxel_spacing_mm': [float(v) for v in ts_im.header.get_zooms()],
         'review_only_instances': review_only,
         'licence_evidence': {'input': 'NLM Terms and Conditions (no licence since July 2019; attribution "Courtesy of the U.S. National Library of Medicine")',
                              'models': ['TotalSegmentator task total: Apache-2.0', 'MOOSE 3.2.2: Apache-2.0 code, CC BY 4.0 weights', 'Skellytour: Apache-2.0 code; weight licence to confirm (paper states CC BY 4.0)']},
         'citation': ['Wasserthal et al. 2023, https://doi.org/10.1148/ryai.230024', 'MOOSE, https://github.com/ENHANCE-PET/MOOSE', 'Skellytour, Wardell et al. 2025, Radiology: Artificial Intelligence',
                      'HRA united-female v1.5, https://lod.humanatlas.io/ref-organ/united-female/v1.5', 'NIH 3D 3DPX-020988, https://3d.nih.gov/entries/3DPX-020988',
                      'NLM Visible Human Project, https://www.nlm.nih.gov/research/visible/visible_human.html']}
(OUT / 'atlas-ct-consensus.json').write_text(json.dumps(atlas, separators=(',', ':')))
(ROOT / 'generated/ct-consensus-qa.json').write_text(json.dumps({'meshes': reports, 'review_only_instances': review_only}, indent=2) + '\n')
print(json.dumps({'meshes': len(parts), 'triangles': atlas['triangles'], 'review_only': len(review_only), 'chunks': len(chunks)}))
