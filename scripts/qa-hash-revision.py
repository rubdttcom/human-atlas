"""Attach geometry_sha256 to the rows of a QA report from the buffers of the git revision that produced it.

Usage: python scripts/qa-hash-revision.py REV REPORT OUT [--atlases a,b,...]

Reads public/atlases/<atlas>.json and the referenced .bin chunks from `git show REV:...` (never from the
working tree), digests every part with qa_identity.geometry_digest and writes a copy of REPORT whose rows
carry `geometry_sha256` from that revision. Rows whose (atlas, structure) does not exist at REV are left
without a digest and are listed on stderr; they can never be carried over. This is the only accepted way
to migrate a report that predates the field: the digest comes from the exact bytes measured, not from
aggregate statistics.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_identity import geometry_digest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def show(rev, path):
    return subprocess.run(['git', '-C', str(ROOT), 'show', f'{rev}:{path}'], check=True, capture_output=True).stdout


def digests_at(rev, atlas_name):
    atlas = json.loads(show(rev, f'public/atlases/{atlas_name}.json'))
    buffers = [show(rev, 'public' + c['url']) for c in atlas['chunks']]
    out = {}
    for part in atlas['parts']:
        data = buffers[part['chunk']]
        vertices = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3)
        faces = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3)
        out[part['id']] = geometry_digest(vertices, faces)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    rev, report_path, out_path = args[0], Path(args[1]), Path(args[2])
    report = json.loads(report_path.read_text())
    atlases = sys.argv[sys.argv.index('--atlases') + 1].split(',') if '--atlases' in sys.argv else sorted({r['atlas'] for r in report['structures']})
    digests = {a: digests_at(rev, a) for a in atlases}
    missing, done = [], 0
    for row in report['structures']:
        digest = digests.get(row['atlas'], {}).get(row['structure'])
        if digest is None:
            row.pop('geometry_sha256', None)
            missing.append((row['atlas'], row['structure']))
        else:
            row['geometry_sha256'] = digest
            done += 1
    report['geometry_sha256_from_revision'] = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', rev], check=True, capture_output=True, text=True).stdout.strip()
    out_path.write_text(json.dumps(report, indent=2) + '\n')
    for atlas, structure in missing:
        print(f'no geometry at {rev}: {atlas} {structure}', file=sys.stderr)
    print(json.dumps({'revision': rev, 'rows_hashed': done, 'rows_without_geometry_at_revision': len(missing), 'out': str(out_path)}))


if __name__ == '__main__':
    main()
