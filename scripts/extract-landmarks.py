"""Extract reproducible bony landmarks from shipped lower-limb and pelvic meshes.

Landmarks are computed by explicit geometric rules on the optimized viewer meshes
(stage frame: +x subject left, +y superior, +z anterior, metres). They are not
manually marked by an anatomist. Every landmark records its rule, the meshes it
came from and a `manual_review: pending` flag so that a reviewer can replace or
confirm it. Femoral head centres are sphere fits and lie inside the bone.
"""
import json
from pathlib import Path
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'transforms/landmarks'
OUT.mkdir(parents=True, exist_ok=True)
MARKER = 'scripts/extract-landmarks.py (geometric rule on optimized viewer mesh)'


def load(atlas_name):
    atlas = json.loads((ROOT / 'public/atlases' / (atlas_name + '.json')).read_text())
    buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in atlas['chunks']]
    meshes = {}
    for part in atlas['parts']:
        data = buffers[part['chunk']]
        vertices = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3).astype(float)
        faces = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3)
        meshes[part['id']] = (part, vertices, faces)
    return atlas, meshes


def sphere_fit(points):
    """Algebraic least-squares sphere; returns centre and radius."""
    a = np.hstack([2 * points, np.ones((len(points), 1))])
    b = np.einsum('ij,ij->i', points, points)
    solution, *_ = np.linalg.lstsq(a, b, rcond=None)
    centre = solution[:3]
    radius = float(np.sqrt(solution[3] + centre @ centre))
    return centre, radius


def femoral_head(vertices, side):
    """Sphere fit to the medial part of the proximal 60 mm of the femur, refined twice."""
    top = vertices[:, 1].max()
    slab = vertices[vertices[:, 1] > top - 0.060]
    medial_sign = -1 if side == 'left' else 1   # medial = towards x = 0 (+x is subject left)
    x = slab[:, 0] * medial_sign
    candidates = slab[x > np.median(x)]           # the medial half of the slab: head and neck, not the trochanter
    centre, radius = sphere_fit(candidates)
    for _ in range(3):
        distance = np.linalg.norm(vertices - centre, axis=1)
        shell = vertices[np.abs(distance - radius) < 0.25 * radius]
        centre, radius = sphere_fit(shell)
    residual = np.abs(np.linalg.norm(shell - centre, axis=1) - radius)
    return centre, radius, float(np.sqrt(np.mean(residual ** 2)))


SLAB = 0.003  # extreme-slab thickness, about one CT slice (2.34 mm); centroids resist voxel-flat extremes


def extreme(points, axis, sign):
    """Centroid of the vertices within SLAB of the extreme along `axis` in direction `sign`."""
    values = points[:, axis] * sign
    return points[values > values.max() - SLAB].mean(axis=0)


def epicondyles(vertices, side):
    bottom = vertices[:, 1].min()
    slab = vertices[vertices[:, 1] < bottom + 0.060]
    lateral_sign = 1 if side == 'left' else -1
    lateral = extreme(slab, 0, lateral_sign)
    medial = extreme(slab, 0, -lateral_sign)
    return medial, lateral


def medial_malleolus(vertices, side):
    """Most distal tibial vertex among the medial third of the distal 40 mm."""
    bottom = vertices[:, 1].min()
    slab = vertices[vertices[:, 1] < bottom + 0.040]
    medial_sign = -1 if side == 'left' else 1
    x = slab[:, 0] * medial_sign
    medial_third = slab[x > np.quantile(x, 2 / 3)]
    return extreme(medial_third, 1, -1)


def lateral_malleolus(vertices):
    return extreme(vertices, 1, -1)


def asis(vertices):
    """Most anterior vertex of the superior half of the hip bone (iliac region)."""
    y_mid = (vertices[:, 1].min() + vertices[:, 1].max()) / 2
    upper = vertices[vertices[:, 1] > y_mid]
    return extreme(upper, 2, 1)


def iliac_crest_apex(vertices):
    """Centroid of the 3 mm most superior slab of the hip bone."""
    return extreme(vertices, 1, 1)


def pubic_symphysis_facet(vertices, side):
    """Centroid of the 3 mm most medial slab of the anterior-inferior quarter of the hip bone."""
    y_mid = (vertices[:, 1].min() + vertices[:, 1].max()) / 2
    z_mid = (vertices[:, 2].min() + vertices[:, 2].max()) / 2
    quarter = vertices[(vertices[:, 1] < y_mid) & (vertices[:, 2] > z_mid)]
    medial_sign = -1 if side == 'left' else 1
    return extreme(quarter, 0, medial_sign)


def ischial_tuberosity(vertices):
    """Most inferior vertex of the hip bone (the ischial tuberosity is its lowest point)."""
    return extreme(vertices, 1, -1)


def side_of(name):
    lower = name.lower()
    return 'left' if 'left' in lower or lower.endswith('_l') else 'right' if 'right' in lower or lower.endswith('_r') else None


def split_bilateral(vertices, faces, name):
    """Split a grouped bilateral CT label into left/right by connected components, then centroid sign."""
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    pieces = sorted(mesh.split(only_watertight=False), key=lambda m: -len(m.faces))
    sides = {'left': [], 'right': []}
    for piece in pieces:
        sides['left' if piece.centroid[0] > 0 else 'right'].append(piece)
    result = {}
    if not sides['left'] or not sides['right']:
        # One connected label spanning the midline (e.g. hip bones fused to the sacrum by voxels): split vertices by sign.
        for side, sign in (('left', 1), ('right', -1)):
            result[side] = (vertices[vertices[:, 0] * sign > 0], 0, len(pieces))
        return result
    for side, parts in sides.items():
        # Keep components that are at least 5 % of the side's largest component; drops speckle.
        largest = len(parts[0].faces)
        kept = [p for p in parts if len(p.faces) >= 0.05 * largest]
        result[side] = (np.vstack([p.vertices for p in kept]), len(kept), len(parts))
    return result


def record(name, side, point, rule, assets, extra=None, vertices=None):
    item = {'landmark': name, 'side': side, 'point_stage_m': [float(v) for v in point], 'rule': rule,
            'source_assets': assets, 'marked_by': MARKER, 'view': 'not applicable (computed, not picked in a view)',
            'manual_review': 'pending'}
    if vertices is not None:
        # Slab centroids can sit off the surface across a curved crest; the distance is recorded so reviewers can judge it.
        item['nearest_source_vertex_mm'] = float(np.min(np.linalg.norm(vertices - np.asarray(point), axis=1)) * 1000)
    if extra:
        item.update(extra)
    return item


def femur_landmarks(vertices, side, assets):
    centre, radius, rms = femoral_head(vertices, side)
    medial, lateral = epicondyles(vertices, side)
    return [record('femoral_head_centre', side, centre, 'least-squares sphere fit to the medial half of the proximal 60 mm, refined on the sphere shell', assets,
                   {'sphere_radius_mm': radius * 1000, 'sphere_fit_rms_mm': rms * 1000, 'on_surface': False}),
            record('medial_epicondyle', side, medial, 'centroid of the 3 mm most medial slab of the distal 60 mm', assets, vertices=vertices),
            record('lateral_epicondyle', side, lateral, 'centroid of the 3 mm most lateral slab of the distal 60 mm', assets, vertices=vertices)]


def export(atlas_name, landmarks, notes):
    payload = {'atlas': atlas_name, 'frame': 'viewer stage of the source atlas (+x subject left, +y superior, +z anterior, metres)',
               'method': 'automatic geometric rules; see each landmark', 'manual_review': 'pending', 'notes': notes,
               'landmarks': landmarks}
    (OUT / (atlas_name + '.json')).write_text(json.dumps(payload, indent=2) + '\n')
    print(f'{atlas_name}: {len(landmarks)} landmarks')
    for item in landmarks:
        print(f"  {item['side']:5s} {item['landmark']:22s} {np.round(np.array(item['point_stage_m']) * 1000, 1)}"
              + (f"  r={item['sphere_radius_mm']:.1f} mm rms={item['sphere_fit_rms_mm']:.2f} mm" if 'sphere_radius_mm' in item else ''))


# Denver VHF: individual bones per side.
_, denver = load('denver-vhf')
denver_landmarks = []
for side, folder in (('left', 'Left'), ('right', 'Right')):
    femur_id = f'DENVER:VHF:{folder}_Bone_Femur'
    denver_landmarks += femur_landmarks(denver[femur_id][1], side, [femur_id])
    tibia_id = f'DENVER:VHF:{folder}_Bone_Tibia'
    denver_landmarks.append(record('medial_malleolus', side, medial_malleolus(denver[tibia_id][1], side), 'centroid of the 3 mm most distal slab among the medial third of the distal 40 mm of the tibia', [tibia_id], vertices=denver[tibia_id][1]))
    fibula_id = f'DENVER:VHF:{folder}_Bone_Fibula'
    denver_landmarks.append(record('lateral_malleolus', side, lateral_malleolus(denver[fibula_id][1]), 'centroid of the 3 mm most distal slab of the fibula', [fibula_id], vertices=denver[fibula_id][1]))
    pelvis_id = f'DENVER:VHF:{folder}_Bone_Pelvis'
    denver_landmarks.append(record('anterior_superior_iliac_spine', side, asis(denver[pelvis_id][1]), 'centroid of the 3 mm most anterior slab of the superior half of the hip bone', [pelvis_id], vertices=denver[pelvis_id][1]))
    denver_landmarks.append(record('ischial_tuberosity', side, ischial_tuberosity(denver[pelvis_id][1]), 'centroid of the 3 mm most inferior slab of the hip bone', [pelvis_id], vertices=denver[pelvis_id][1]))
    denver_landmarks.append(record('iliac_crest_apex', side, iliac_crest_apex(denver[pelvis_id][1]), 'centroid of the 3 mm most superior slab of the hip bone', [pelvis_id], vertices=denver[pelvis_id][1]))
    denver_landmarks.append(record('pubic_symphysis_facet', side, pubic_symphysis_facet(denver[pelvis_id][1], side), 'centroid of the 3 mm most medial slab of the anterior-inferior quarter of the hip bone', [pelvis_id], vertices=denver[pelvis_id][1]))
export('denver-vhf', denver_landmarks, ['Bones are individual manual segmentations; sides come from the archive folder, with display names normalized.'])

# TCIA 003: grouped bilateral labels, split by connected components.
_, tcia = load('tcia')
by_name = {part['name']: (part, v, f) for part, v, f in tcia.values()}
tcia_landmarks = []
splits = {name: split_bilateral(by_name[name][1], by_name[name][2], name) for name in ('Femur', 'Tibia', 'Fibula', 'Pelvis')}
for side in ('left', 'right'):
    femur, kept, total = splits['Femur'][side]
    assets = [by_name['Femur'][0]['id']]
    tcia_landmarks += femur_landmarks(femur, side, assets)
    tibia = splits['Tibia'][side][0]
    tcia_landmarks.append(record('medial_malleolus', side, medial_malleolus(tibia, side), 'centroid of the 3 mm most distal slab among the medial third of the distal 40 mm of the tibia (side split by connected components)', [by_name['Tibia'][0]['id']], vertices=tibia))
    fibula = splits['Fibula'][side][0]
    tcia_landmarks.append(record('lateral_malleolus', side, lateral_malleolus(fibula), 'centroid of the 3 mm most distal slab of the fibula (side split by connected components)', [by_name['Fibula'][0]['id']], vertices=fibula))
    pelvis = splits['Pelvis'][side][0]
    # The grouped CT pelvis label can include the sacrum; restrict hip-bone rules to vertices lateral to 40 mm from the midline.
    hip = pelvis[np.abs(pelvis[:, 0]) > 0.040]
    tcia_landmarks.append(record('anterior_superior_iliac_spine', side, asis(hip), 'centroid of the 3 mm most anterior slab of the superior half of the hip bone, vertices more than 40 mm lateral of the midline (side split by connected components)', [by_name['Pelvis'][0]['id']], vertices=pelvis))
    tcia_landmarks.append(record('ischial_tuberosity', side, ischial_tuberosity(hip), 'centroid of the 3 mm most inferior slab of the hip bone, vertices more than 40 mm lateral of the midline (side split by connected components)', [by_name['Pelvis'][0]['id']], vertices=pelvis))
    tcia_landmarks.append(record('iliac_crest_apex', side, iliac_crest_apex(hip), 'centroid of the 3 mm most superior slab of the hip bone, vertices more than 40 mm lateral of the midline (side split by connected components)', [by_name['Pelvis'][0]['id']], vertices=pelvis))
    tcia_landmarks.append(record('pubic_symphysis_facet', side, pubic_symphysis_facet(pelvis, side), 'centroid of the 3 mm most medial slab of the anterior-inferior quarter of the side-split pelvis label', [by_name['Pelvis'][0]['id']], vertices=pelvis))
components = {name: {side: {'components_kept': s[side][1], 'components_total': s[side][2]} for side in s} for name, s in splits.items()}
export('tcia-003', tcia_landmarks, ['Grouped bilateral CT labels were split by connected components and assigned to a side by centroid sign; components smaller than 5 % of the largest were dropped as speckle.',
                                    'Automatic segmentation, not manually reviewed; landmarks inherit any segmentation error.', {'component_split': components}])

# HRA female reference: individual bones per side (compact bone surfaces).
_, hra = load('hra-female')
hra_landmarks = []
for side, suffix in (('left', 'L'), ('right', 'R')):
    femur_id = f'VH_F_femur_{suffix}'
    hra_landmarks += femur_landmarks(hra[femur_id][1], side, [femur_id])
    tibia_id = f'VH_F_tibia_{suffix}'
    hra_landmarks.append(record('medial_malleolus', side, medial_malleolus(hra[tibia_id][1], side), 'centroid of the 3 mm most distal slab among the medial third of the distal 40 mm of the tibia', [tibia_id], vertices=hra[tibia_id][1]))
    fibula_id = f'VH_F_fibula_{suffix}'
    hra_landmarks.append(record('lateral_malleolus', side, lateral_malleolus(hra[fibula_id][1]), 'centroid of the 3 mm most distal slab of the fibula', [fibula_id], vertices=hra[fibula_id][1]))
    ilium_id = f'VH_F_ilium_compact_bone_{suffix}'
    hra_landmarks.append(record('anterior_superior_iliac_spine', side, asis(hra[ilium_id][1]), 'centroid of the 3 mm most anterior slab of the superior half of the ilium compact bone', [ilium_id], vertices=hra[ilium_id][1]))
    ischium_id = f'VH_F_ischium_compact_bone_{suffix}'
    hra_landmarks.append(record('ischial_tuberosity', side, ischial_tuberosity(hra[ischium_id][1]), 'centroid of the 3 mm most inferior slab of the ischium compact bone', [ischium_id], vertices=hra[ischium_id][1]))
    hra_landmarks.append(record('iliac_crest_apex', side, iliac_crest_apex(hra[ilium_id][1]), 'centroid of the 3 mm most superior slab of the ilium compact bone', [ilium_id], vertices=hra[ilium_id][1]))
    pubis_id = f'VH_F_pubis_compact_bone_{suffix}'
    hra_landmarks.append(record('pubic_symphysis_facet', side, extreme(hra[pubis_id][1], 0, -1 if side == 'left' else 1), 'centroid of the 3 mm most medial slab of the pubis compact bone', [pubis_id], vertices=hra[pubis_id][1]))
export('hra-female', hra_landmarks, ['Reference assembly; the donor of each bone is not established. Used only as a cross-check of the organ-proxy registration.'])
