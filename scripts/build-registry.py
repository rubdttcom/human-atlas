"""Build provenance and coverage from the actual source manifests, offline."""
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'd72b4f6db42e41a8db84b1c19ff6d86ee7b65284'
UPSTREAM = 'https://github.com/ashemag/human-atlas'


def write_json(path, data):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def write_csv(path, fields, rows):
    with (ROOT / path).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def normalize(term):
    return re.sub(r'^(FMA|UBERON):?(\d+)$', r'\1:\2', term)


def laterality(name):
    sides = [side for side in ('left', 'right') if re.search(r'\b' + side + r'\b', name, re.I)]
    return sides[0] if len(sides) == 1 else 'unspecified'


with (ROOT / 'datasets.csv').open() as handle:
    sources = list(csv.DictReader(handle))
source_map = {s['id']: s for s in sources}
write_json('registry/sources.json', sources)
write_json('registry/licences.json', {s['id']: {
    'license': s['license'], 'url': s['license_url'],
    'redistributable': s['redistributable'], 'commercial_use': s['commercial_use'],
    'review_status': 'recorded-source-declaration' if s['license'] == 'CC-BY-4.0' else 'pending-per-asset-review',
} for s in sources})
qa_path = ROOT / 'generated/qa-report.json'
qa_records = {(r['atlas'], r['structure']): r for r in json.loads(qa_path.read_text())['structures']} if qa_path.exists() else {}
write_json('registry/donors.json', [
    {'id': 'VHF', 'sex': 'female', 'source': 'https://digitalcommons.du.edu/visiblehuman/', 'age_years': 59},
    {'id': 'TARO', 'sex': 'male', 'source': 'https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html'},
    {'id': 'hra-female-assembly', 'sex': 'unknown-per-component', 'single_donor': False},
])
transforms = {
    'hra-native-to-stage': {
        'type': 'translation', 'from': 'HRA united-female v1.5 native', 'to': 'HRA viewer stage',
        'matrix_row_major': [1, 0, 0, 0, 0, 1, 0, 0.794760942, 0, 0, 1, 0, 0, 0, 0, 1],
        'units': 'metres', 'evidence': f'{UPSTREAM}/blob/{REVISION}/scripts/convert-female.py',
        'canonical_registration': False, 'review_status': 'source-script-verified',
        'landmarks': [], 'rms': None, 'hausdorff': None,
    },
    'bp3d-to-stage': {
        'type': 'axis-unit-normalization-and-translation', 'from': 'BodyParts3D 4.0',
        'to': 'BodyParts3D viewer stage', 'evidence': f'{UPSTREAM}/blob/7a383d3/scripts/convert-anatomy.py',
        'canonical_registration': False, 'review_status': 'inherited-source-conversion',
        'landmarks': [], 'rms': None, 'hausdorff': None,
    },
}
configs = [
    ('hra-female', 'atlas-female.json', 'hra-native-to-stage', REVISION),
    ('bodyparts3d', 'atlas.json', 'bp3d-to-stage', '7a383d3ee2759e3ddf157c704fb8814fd0c50bcb'),
]
tcia_path = ROOT / 'public/models/atlas-tcia-female.json'
if tcia_path.exists():
    tcia = json.loads(tcia_path.read_text())
    transforms['tcia-voxel-to-stage'] = {
        'type': 'affine-axis-unit-normalization', 'from': 'TCIA 003 voxel indices', 'to': 'TCIA 003 viewer stage',
        'matrix_row_major': sum(tcia['voxel_to_stage'], []), 'canonical_registration': False,
        'review_status': 'header-derived; anatomical-review-pending', 'units': 'metres',
        'landmarks': [], 'rms': None, 'hausdorff': None,
    }
    configs.append(('tcia', 'atlas-tcia-female.json', 'tcia-voxel-to-stage', tcia['input_sha256']))
    donors = json.loads((ROOT / 'registry/donors.json').read_text())
    donors.append({'id': 'Healthy-Total-Body-CTs-003', 'sex': 'female', 'metadata': tcia['donor_metadata'],
                   'evidence': 'data/raw/tcia/demographics.xlsx'})
    write_json('registry/donors.json', donors)
denver_path = ROOT / 'public/models/atlas-denver-female.json'
if denver_path.exists():
    denver = json.loads(denver_path.read_text())
    transforms['denver-image-to-stage'] = {
        'type': 'axis-permutation-unit-scale-translation', 'from': 'Denver aligned VHF image frame (mm)',
        'to': 'Denver VHF viewer stage', 'matrix_row_major': sum(denver['source_to_stage'], []), 'units': 'metres',
        'canonical_registration': False, 'review_status': 'empirical-axis-check; anatomical-review-pending',
        'evidence': denver['frame_evidence'], 'landmarks': [], 'rms': None, 'hausdorff': None,
    }
    configs.append(('denver-vhf', 'atlas-denver-female.json', 'denver-image-to-stage', denver['input_sha256']))
    donors = json.loads((ROOT / 'registry/donors.json').read_text())
    for donor in donors:
        if donor['id'] == 'VHF':
            donor['evidence'] = ['Andreassen et al. 2022, https://doi.org/10.1038/s41597-022-01905-2',
                                 'data/raw/denver/download-manifest.json']
            donor['datasets'] = ['denver-vhf']
    write_json('registry/donors.json', donors)
write_json('transforms/source-to-stage.json', transforms)
all_records = []
catalog = {}
crosswalk = []
atlas_summaries = []
for source_id, filename, transform, revision in configs:
    raw = (ROOT / 'public/models' / filename).read_bytes()
    atlas = json.loads(raw)
    source = source_map[source_id]
    hashes = {}
    for chunk in atlas['chunks']:
        data = (ROOT / 'public' / chunk['url'].lstrip('/')).read_bytes()
        if len(data) != chunk['bytes']:
            raise ValueError(f"Invalid chunk length: {chunk['url']}")
        hashes[chunk['url']] = hashlib.sha256(data).hexdigest()
    records = []
    for part in atlas['parts']:
        term = normalize(part['conceptId'])
        side = laterality(part['name'])
        # Laterality remains explicit even when a source uses a non-lateralized ontology term.
        canonical = term + ('|' + side if side != 'unspecified' else '')
        catalog.setdefault(canonical, {
            'canonical_id': canonical, 'name': part['name'], 'uberon': term if term.startswith('UBERON:') else '',
            'fma': term if term.startswith('FMA:') else '', 'ta2': '', 'system': part['system'],
            'laterality': side, 'scope': 'direct-source-geometry',
        })
        record = {
            'id': source_id + ':' + part['id'], 'structure_id': canonical, 'name': part['name'],
            'source': source_id, 'source_asset': part['id'], 'source_url': source['url'],
            'source_revision': revision, 'source_manifest_sha256': hashlib.sha256(raw).hexdigest(),
            'source_chunk': atlas['chunks'][part['chunk']]['url'],
            'source_chunk_sha256': hashes[atlas['chunks'][part['chunk']]['url']],
            'source_sex': 'male' if source_id == 'bodyparts3d' else 'unknown-per-component',
            'reference_sex': atlas['sex'],
            'source_donor': 'TARO' if source_id == 'bodyparts3d' else 'hra-female-assembly',
            'geometry_type': 'reference_template' if source_id == 'bodyparts3d' else 'reference_assembly',
            'canonical_space': None, 'display_space': transforms[transform]['to'],
            'registration': {'type': 'native-VHF-image-frame; canonical VHF space not yet defined' if source_id == 'denver-vhf' else 'unregistered-to-VHF',
                             'display_transform_id': transform, 'transform_id': None},
            'confidence': None, 'confidence_basis': 'anatomical review pending',
            'license': source['license'], 'license_url': source['license_url'],
            'redistributable': source['redistributable'] == 'true',
            'commercial_use': source['commercial_use'] == 'true',
            'laterality': side, 'ontology_mapping': 'inherited-source-id',
            'qa_status': 'source-buffer-checked; anatomical-review-pending',
            'adaptations': atlas.get('optimized', {}),
            'notes': 'Male reference template; not registered to a female donor.' if source_id == 'bodyparts3d'
            else 'Female reference assembly; component donor and biological sex are not established by the assembly label.',
        }
        record.update(part.get('source_metadata', {}))
        if (source_id, part['id']) in qa_records:
            record['geometry_qa'] = qa_records[(source_id, part['id'])]
        records.append(record)
        part['provenance'] = record
        crosswalk.append({'source': source_id, 'source_asset': part['id'], 'source_term': part['conceptId'],
                          'canonical_id': canonical, 'method': 'identifier-format-normalization; explicit-name-laterality'})
    direct_ids = {normalize(p['conceptId']) for p in atlas['parts']}
    for concept in atlas['concepts']:
        term = normalize(concept['id'])
        if term in direct_ids or term.startswith('HRA:'):
            continue
        catalog.setdefault(term, {'canonical_id': term, 'name': concept['name'], 'fma': term,
                                 'uberon': '', 'ta2': '', 'system': 'aggregate', 'laterality': laterality(concept['name']),
                                 'scope': 'source-hierarchy-concept'})
    for record in records:
        record['alternatives'] = []
    write_json('manifests/' + source_id + '.json', records)
    write_json('public/atlases/' + source_id + '.json', atlas)
    all_records.extend(records)
    atlas_summaries.append({'source': source_id, 'meshes': len(records), 'source_concepts': len(atlas['concepts']),
                            'triangles': atlas['triangles'], 'chunk_hashes': hashes})

by_structure = {}
for record in all_records:
    by_structure.setdefault(record['structure_id'], []).append(record)
coverage = []
for canonical, structure in sorted(catalog.items()):
    candidates = sorted(by_structure.get(canonical, []), key=lambda r: int(source_map[r['source']]['priority']))
    coverage.append({**structure, 'best_available': candidates[0]['id'] if candidates else None,
                     'candidates': [r['id'] for r in candidates],
                     'female_measured': any(r['geometry_type'] == 'manual_segmentation' and r['source_sex'] == 'female' for r in candidates),
                     'female_segmented_unreviewed': any(r['geometry_type'] == 'automatic_segmentation' and r['source_sex'] == 'female' for r in candidates),
                     'female_reference': any(r['source'] == 'hra-female' for r in candidates),
                     'template_only': bool(candidates) and all(r['source'] == 'bodyparts3d' for r in candidates),
                     'registration_ready': False,
                     'status': 'direct-geometry' if candidates else 'no-direct-geometry'})
for source_id, *_ in configs:
    path = ROOT / 'public/atlases' / (source_id + '.json')
    atlas = json.loads(path.read_text())
    for part in atlas['parts']:
        record = part['provenance']
        record['alternatives'] = [r['id'] for r in by_structure[record['structure_id']] if r['id'] != record['id']]
    write_json('public/atlases/' + source_id + '.json', atlas)
    write_json('manifests/' + source_id + '.json', [p['provenance'] for p in atlas['parts']])
write_json('registry/ontology-crosswalk.json', crosswalk)
write_json('registry/canonical-structures.json', list(catalog.values()))
write_json('generated/coverage-matrix.json', coverage)
write_json('public/atlases/coverage-matrix.json', coverage)
write_csv('structures.csv', ['canonical_id', 'name', 'uberon', 'fma', 'ta2', 'system', 'laterality', 'scope'], catalog.values())
write_csv('coverage.csv', ['canonical_structure', 'dataset', 'available', 'sex', 'donor', 'geometry_type', 'quality', 'license_class', 'priority'], [
    {'canonical_structure': r['structure_id'], 'dataset': r['source'], 'available': True, 'sex': r['source_sex'],
     'donor': r['source_donor'], 'geometry_type': r['geometry_type'], 'quality': r['qa_status'],
     'license_class': r['license'], 'priority': source_map[r['source']]['priority']} for r in all_records])
summary = {
    'canonical_catalog_entries': len(catalog), 'source_meshes': len(all_records),
    'female_measured': sum(r['female_measured'] for r in coverage), 'registered_female': 0,
    'female_segmented_unreviewed': sum(r['female_segmented_unreviewed'] for r in coverage),
    'female_reference': sum(r['female_reference'] for r in coverage),
    'template_only': sum(r['template_only'] for r in coverage),
    'without_direct_geometry': sum(not r['candidates'] for r in coverage),
    'atlases': atlas_summaries,
    'limitations': ['Catalog is the imported source union, not the complete human ontology.',
                    'No UBERON/FMA equivalence inferred; no TA2 crosswalk imported.',
                    'No VHF canonical registration or anatomical QA yet. Denver meshes are in the aligned VHF image frame, but no other source is registered to it.',
                    'Best available ranks source evidence but does not authorize spatial composition.'],
}
write_json('generated/coverage-summary.json', summary)
write_json('public/atlases/coverage-summary.json', summary)
print(json.dumps({k: v for k, v in summary.items() if k != 'atlases'}, indent=2))
