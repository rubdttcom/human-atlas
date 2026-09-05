"""Check reviewer registries: referenced ids exist, statuses are allowed, and nothing claims a review that was not recorded."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
status = json.loads((ROOT / 'registry/review-status.json').read_text())
landmark_reviews = json.loads((ROOT / 'registry/landmark-review.json').read_text())
allowed = set(status['allowed_status'])
mesh_ids = set()
for name in ('hra-female', 'bodyparts3d', 'tcia', 'denver-vhf', 'nlm-vhf-ct', 'composed'):
    path = ROOT / 'public/atlases' / (name + '.json')
    if path.exists():
        mesh_ids |= {p['provenance']['id'] for p in json.loads(path.read_text())['parts']}
transform_ids = {json.loads(p.read_text())['id'] for p in (ROOT / 'transforms').glob('*-to-vhf.json')}
transform_ids |= {'hra-head-to-vhf'}
assert status['default']['status'] == 'pending'
for key, entry in status['structures'].items():
    assert entry['status'] in allowed, key
    assert key in mesh_ids or key.split('|')[0].startswith(('UBERON:', 'FMA:')), key
    assert entry.get('reviewer') in {r['id'] for r in status['reviewers']}, f'{key}: reviewer not registered'
for issue in status['known_issues']:
    assert issue['status'] in allowed, issue['id']
    ident = issue['id'].split(':', 1)[1] if issue['id'].startswith('hra-female:hra-') else issue['id']
    assert issue['id'] in mesh_ids or ident in transform_ids, issue['id']
landmarks = set()
for name in ('denver-vhf', 'tcia-003', 'hra-female'):
    for item in json.loads((ROOT / 'transforms/landmarks' / (name + '.json')).read_text())['landmarks']:
        landmarks.add((name, item['side'], item['landmark']))
for review in landmark_reviews['reviews']:
    assert review.get('reviewer'), 'landmark review without reviewer'
    for item in review['landmarks']:
        assert item['decision'] in ('pending', 'confirmed', 'rejected'), item
        assert any((n, item['side'], item['landmark']) in landmarks for n in ('denver-vhf', 'tcia-003', 'hra-female')), item
reviewed = sum(e['status'] != 'pending' for e in status['structures'].values())
print(f"Review registries consistent: {reviewed} reviewed structures, {len(status['known_issues'])} known issues, {len(landmark_reviews['reviews'])} landmark reviews; all other meshes pending.")
