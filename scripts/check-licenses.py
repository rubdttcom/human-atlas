"""Audit licences of every geometry actually referenced by each shipped atlas."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--target', choices=['open-clean', 'open-sharealike', 'research-full'], default='open-clean')
args = parser.parse_args()
# NLM Visible Human images are public-domain U.S. Government works released under the NLM Terms and Conditions
# (no licence since July 2019; attribution "Courtesy of the U.S. National Library of Medicine"; redistribution allowed).
allowed = {'CC0-1.0', 'CC-BY-4.0', 'CC-BY-3.0', 'MIT', 'BSD-3-Clause', 'Zlib', 'NLM-Terms-and-Conditions'}
if args.target in ('open-sharealike', 'research-full'):
    allowed |= {'CC-BY-SA-4.0'}
if args.target == 'research-full':
    allowed |= {'CC-BY-NC-4.0', 'CC-BY-NC-SA-4.0'}
errors, records = [], []
for filename in ('hra-female', 'bodyparts3d', 'tcia', 'denver-vhf', 'nlm-vhf-ct', 'composed'):
    atlas = json.loads((ROOT / 'public/atlases' / (filename + '.json')).read_text())
    for part in atlas['parts']:
        record = part.get('provenance', {})
        eligible = record.get('license') in allowed and record.get('redistributable') is True
        if args.target != 'research-full':
            eligible = eligible and record.get('commercial_use') is True
        if not record.get('source_url') or not record.get('license_url') or not record.get('source_chunk_sha256'):
            eligible = False
        if not eligible:
            errors.append(f"{filename}: {part['id']}: licence evidence incomplete or incompatible")
        records.append({'atlas': filename, 'structure': part['id'], 'source': record.get('source'),
                        'license': record.get('license'), 'eligible': eligible})
report = {'target': args.target, 'mesh_references': len(records), 'errors': errors, 'records': records,
          'scope': 'Shipped geometry only. Candidate datasets are not licensed by this report.'}
(ROOT / 'generated' / f'licence-report-{args.target}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'records'}, indent=2))
raise SystemExit(bool(errors))
