"""Convert the Denver Visible Human Female final STL models into traceable viewer geometry.

Source: Andreassen et al., "Visible Human Female", University of Denver Center for
Orthopaedic Biomechanics, CC BY 4.0 (README inside the archive). The "Final 3D STL
Models" are manually segmented cryosection geometry after smoothing and overclosure
correction, in the aligned VHF image frame (millimetres). Every STL is converted once,
welded, and recorded with its archive member, CRC and SHA-256.
"""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/denver'
OUT = ROOT / 'public/models'
ARCHIVE = RAW / 'final-stl-models.zip'
archive_hash = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
manifest = json.loads((RAW / 'download-manifest.json').read_text())
download = next(r for r in manifest if r['local'].endswith('final-stl-models.zip'))
assert download['sha256'] == archive_hash, 'Archive differs from the recorded download'
archive = zipfile.ZipFile(ARCHIVE)
members = sorted(n for n in archive.namelist() if n.lower().endswith('.stl'))
readme = archive.read('Final 3D STL Models-stl/README.txt').decode('utf-8', 'replace')
assert 'Creative Commons Attribution 4.0' in readme
pattern = re.compile(r'^Final 3D STL Models-stl/(Left|Right)/VHF_(Left|Right)_(Bone|Muscle|Cartilage|Ligament|Fat)_([A-Za-z0-9]+)_smooth\.stl$')
SYSTEMS = {'Bone': 'skeletal', 'Muscle': 'muscular', 'Cartilage': 'connective', 'Ligament': 'connective', 'Fat': 'tissue'}
MIDLINE = {'Sacrum', 'Coccyx'}
ACRONYMS = {'ACL', 'PCL', 'MCL', 'LCL'}
# Display spelling only; the source label is preserved verbatim in source_label and archive_member.
SPELLING = {'Calcaneous': 'Calcaneus', 'Illiacus': 'Iliacus', 'Semitendonosus': 'Semitendinosus', 'QuadratisFemoris': 'QuadratusFemoris',
            # The two sides use different file labels for the same muscle heads.
            'BicepsFemorisLong': 'BicepsFemorisLongHead', 'BicepsFemorisShort': 'BicepsFemorisShortHead'}


def words(label):
    if label in ACRONYMS:
        return label
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', label).lower()


def display_name(side, tissue, label):
    text = words(SPELLING.get(label, label))
    if label in MIDLINE:
        return label
    if tissue == 'Cartilage':
        return f'{side} {text} cartilage'
    if tissue == 'Ligament':
        return f'{side} {text}' if label in ACRONYMS else f'{side} {text} ligament'
    return f'{side} {text}'


# Empirical frame check: +x points to the subject's right (left pelvis has the smaller x),
# +y is anterior (patella anterior to femur shaft), +z is superior (pelvis above calcaneus).
def load(member):
    mesh = trimesh.load(io.BytesIO(archive.read(member)), file_type='stl', process=False)
    mesh.merge_vertices()
    return mesh


meshes = {}
for member in members:
    match = pattern.match(member)
    assert match, member
    meshes[member] = (match, load(member))
centroid = lambda key: next(m.centroid for member, (match, m) in meshes.items() if key in member)
assert centroid('Left_Bone_Pelvis')[0] < centroid('Right_Bone_Pelvis')[0], 'expected +x toward subject right'
assert centroid('Left_Bone_Patella')[1] > centroid('Left_Bone_Femur')[1], 'expected +y anterior'
assert centroid('Left_Bone_Pelvis')[2] > centroid('Left_Bone_Calcaneous')[2], 'expected +z superior'
femur = next(m for member, (match, m) in meshes.items() if 'Left_Bone_Femur' in member)
femur_length_mm = float((femur.bounds[1] - femur.bounds[0]).max())
assert 380 < femur_length_mm < 520, f'femur extent {femur_length_mm} mm is not consistent with millimetre units'
lows = np.min([m.bounds[0] for _, m in meshes.values()], axis=0)
highs = np.max([m.bounds[1] for _, m in meshes.values()], axis=0)
# Source (x right, y anterior, z superior, mm) -> viewer stage (x left, y up, z anterior, m).
rotation = np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float)
matrix = rotation * .001
matrix[3, 3] = 1
matrix[0, 3] = (lows[0] + highs[0]) / 2 * .001          # centre laterally on the stage
matrix[1, 3] = -lows[2] * .001                          # lowest surface point rests on the ground plane
matrix[2, 3] = -(lows[1] + highs[1]) / 2 * .001         # centre antero-posteriorly

parts, concepts, chunks, reports = [], [], [], []
blob = bytearray()


def append(values):
    while len(blob) % 4:
        blob.append(0)
    offset = len(blob)
    blob.extend(values.tobytes())
    return offset


def flush():
    if not blob:
        return
    name = f'denver-source-{len(chunks)}.bin'
    (OUT / name).write_bytes(blob)
    chunks.append({'url': '/models/' + name, 'bytes': len(blob)})
    blob.clear()


groups = {}
for member, (match, mesh) in meshes.items():
    folder, side, tissue, label = match.groups()
    assert folder == side
    raw = archive.read(member)
    info = archive.getinfo(member)
    vertices = trimesh.transform_points(mesh.vertices, matrix)
    mesh = trimesh.Trimesh(vertices=vertices, faces=mesh.faces, process=False)
    winding_reversed = bool(mesh.volume < 0)
    if winding_reversed:
        mesh.invert()
    pos = np.asarray(mesh.vertices, dtype='<f4')
    normal = np.asarray(np.clip(mesh.vertex_normals * 32767, -32767, 32767), dtype='<i2')
    indices = np.asarray(mesh.faces, dtype='<u4').ravel()
    if len(blob) > 6_000_000:
        flush()
    stem = f'{side}_{tissue}_{label}'
    identity = f'DENVER:VHF:{stem}'
    laterality = 'midline' if label in MIDLINE else side.lower()
    part = {'id': identity, 'name': display_name(side, tissue, label), 'conceptId': identity, 'system': SYSTEMS[tissue],
            'chunk': len(chunks), 'positions': append(pos), 'normals': append(normal), 'indices': append(indices),
            'vertexCount': len(pos), 'indexCount': len(indices), 'bounds': [pos.min(axis=0).tolist(), pos.max(axis=0).tolist()],
            'source_metadata': {'source_sex': 'female', 'source_donor': 'VHF', 'geometry_type': 'manual_segmentation',
                                'processing_stage': 'final: smoothed and overclosure-corrected',
                                'archive_member': member, 'archive_crc32': info.CRC, 'stl_sha256': hashlib.sha256(raw).hexdigest(),
                                'stl_bytes': len(raw), 'source_label': label, 'tissue_class': tissue, 'source_folder': folder, 'display_spelling_corrected': label in SPELLING,
                                'laterality': laterality, 'source_units': 'mm',
                                'ontology_mapping': 'dataset-local-label; ontology crosswalk pending',
                                'notes': ('Manually segmented from the NLM Visible Human Female cryosections by the University of Denver; '
                                          'final surfaces are smoothed and overclosure-corrected, not raw segmentation. '
                                          + ('Midline structure stored in the Left folder by the source. ' if label in MIDLINE else '')
                                          + 'Coordinates are the aligned VHF image frame; no other donor is mixed in this view.')}}
    parts.append(part)
    concepts.append({'id': identity, 'name': part['name'], 'elements': [identity]})
    groups.setdefault(('label', tissue, SPELLING.get(label, label)), []).append(identity)
    if label not in MIDLINE:
        groups.setdefault(('tissue', tissue, side), []).append(identity)
    groups.setdefault(('tissue', tissue), []).append(identity)
    reports.append({'structure': identity, 'archive_member': member, 'triangles': len(indices) // 3, 'vertices': len(pos),
                    'watertight': bool(mesh.is_watertight), 'winding_consistent': bool(mesh.is_winding_consistent),
                    'winding_reversed': winding_reversed, 'volume_m3': float(mesh.volume),
                    'degenerate_faces': int(np.sum(mesh.area_faces < 1e-14)),
                    'self_intersections': 'not-assessed', 'anatomical_review': 'pending'})
    print(f'{stem}: {len(indices)//3} triangles', flush=True)
flush()
for key, elements in groups.items():
    if len(elements) < 2:
        continue
    if key[0] == 'label':
        _, tissue, label = key
        name = words(label) if label in ACRONYMS else words(label).capitalize()
        suffix = ' cartilage' if tissue == 'Cartilage' else ' ligament' if tissue == 'Ligament' and label not in ACRONYMS else ''
        concepts.append({'id': f'DENVER:VHF:group:{tissue}_{label}', 'name': f'{name}{suffix} (both sides)', 'elements': elements})
    elif key[0] == 'tissue' and len(key) == 3:
        concepts.append({'id': f'DENVER:VHF:group:{key[2]}_{key[1]}', 'name': f'{key[2]} lower limb {key[1].lower()}s', 'elements': elements})
    else:
        concepts.append({'id': f'DENVER:VHF:group:{key[1]}', 'name': f'Lower limb {key[1].lower()}s', 'elements': elements})
atlas = {'version': 'Denver Visible Human Female 2022, Final 3D STL Models', 'sex': 'female',
         'source': 'Denver VHF lower limb', 'scope': 'Female donor VHF (NLM Visible Human Female); manual cryosection segmentation of the lower limbs, pelvis to toes; final smoothed surfaces',
         'parts': parts, 'concepts': concepts, 'chunks': chunks, 'triangles': sum(p['indexCount'] // 3 for p in parts),
         'input_sha256': archive_hash, 'download': download, 'source_frame': 'aligned VHF image frame; +x subject right, +y anterior, +z superior; millimetres',
         'frame_evidence': {'left_pelvis_centroid_mm': centroid('Left_Bone_Pelvis').tolist(), 'right_pelvis_centroid_mm': centroid('Right_Bone_Pelvis').tolist(),
                            'left_patella_centroid_mm': centroid('Left_Bone_Patella').tolist(), 'left_femur_centroid_mm': centroid('Left_Bone_Femur').tolist(),
                            'left_calcaneus_centroid_mm': centroid('Left_Bone_Calcaneous').tolist(), 'left_femur_max_extent_mm': femur_length_mm},
         'source_bounds_mm': [lows.tolist(), highs.tolist()], 'source_to_stage': matrix.tolist(),
         'license_evidence': 'Final 3D STL Models-stl/README.txt: Creative Commons Attribution 4.0 International',
         'citation': ['Andreassen et al. 2022, Scientific Data, https://doi.org/10.1038/s41597-022-01905-2',
                      'Andreassen et al. 2022, arXiv, https://doi.org/10.48550/arXiv.2209.06948', 'Dataset DOI https://doi.org/10.56902/COB.vh.2022.1']}
(OUT / 'atlas-denver-female.json').write_text(json.dumps(atlas, separators=(',', ':')))
(ROOT / 'generated/denver-qa.json').write_text(json.dumps(reports, indent=2) + '\n')
print(json.dumps({'meshes': len(parts), 'concepts': len(concepts), 'triangles': atlas['triangles'],
                  'non_watertight': sum(not r['watertight'] for r in reports), 'femur_mm': femur_length_mm}))
