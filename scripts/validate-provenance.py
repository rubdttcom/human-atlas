"""Check source identity and coverage against the files actually shipped."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
records = {}
for source, filename in [('hra-female', 'atlas-female.json'), ('bodyparts3d', 'atlas.json'), ('tcia', 'atlas-tcia-female.json'),
                         ('denver-vhf', 'atlas-denver-female.json')]:
    original = json.loads((ROOT / 'public/models' / filename).read_text())
    enriched = json.loads((ROOT / 'public/atlases' / (source + '.json')).read_text())
    assert len(original['parts']) == len(enriched['parts'])
    chunks = {c['url']: hashlib.sha256((ROOT / 'public' / c['url'].lstrip('/')).read_bytes()).hexdigest()
              for c in original['chunks']}
    for old, new in zip(original['parts'], enriched['parts']):
        assert all(new[key] == value for key, value in old.items()), old['id']
        record = new['provenance']
        assert record['source'] == source
        assert record['source_asset'] == old['id']
        assert record['source_chunk_sha256'] == chunks[record['source_chunk']]
        assert record['canonical_space'] is None
        assert record['registration']['transform_id'] is None
        assert record['confidence'] is None
        assert record['id'] not in records
        records[record['id']] = record
coverage = json.loads((ROOT / 'generated/coverage-matrix.json').read_text())
used = set()
for entry in coverage:
    assert entry['best_available'] in entry['candidates'] or entry['best_available'] is None
    assert not entry['registration_ready']
    measured = [c for c in entry['candidates'] if records[c]['geometry_type'] == 'manual_segmentation' and records[c]['source_sex'] == 'female']
    assert entry['female_measured'] == bool(measured), entry['canonical_id']
    for candidate in measured:
        assert records[candidate]['source'] == 'denver-vhf' and records[candidate]['source_donor'] == 'VHF'
    for candidate in entry['candidates']:
        assert records[candidate]['structure_id'] == entry['canonical_id']
        used.add(candidate)
assert used == set(records)
for record in records.values():
    for alternative in record['alternatives']:
        assert records[alternative]['structure_id'] == record['structure_id']
measured = sum(e['female_measured'] for e in coverage)
print(f'Verified {len(records)} source mesh identities and {len(coverage)} coverage entries ({measured} with measured female geometry); no unverified registration claims in source atlases.')
