"""Origin completeness of the NLM female colour cryosections, kept apart from local integrity.

`scripts/inventory-cryosections.py` (run on rub-pc) proves local integrity: every file on disk matches the SHA-256
manifest that travelled with the download. That manifest is local, so it cannot show that the download is complete
against the origin. This script compares the local inventory with two independent statements of the origin:

  1. `data/raw/nlm-vhf/INDEX`: the NLM Visible Human Project's own recursive directory listing (`ls -lR`, dated
     1 February 1996) shipped with the data set. Its `./Fullcolor/fullbody` section lists every file NLM published,
     with byte sizes.
  2. The current NLM server (`https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/Fullcolor/fullbody/`):
     one HTTP HEAD per file the inventory reports absent, and one per neighbouring present file as a control. The
     server answers 403 for paths it does not serve and 200 for files it serves; directory listings are refused (403),
     so the HEAD probe is the only remote evidence available without downloading.

Writes generated/cryosection-origin-check.json. Slice counts, placeholders and gap thicknesses are recomputed from the
inventory rows here so the numbers in docs/PROGRESS.md have one source. Nothing is downloaded.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'data/raw/nlm-vhf/INDEX'
INVENTORY = ROOT / 'generated/cryosection-inventory.json'
OUT = ROOT / 'generated/cryosection-origin-check.json'
BASE = 'https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/Fullcolor/fullbody/'
SUB_MM = 1 / 3
NLM_DOCUMENTED_SLICES = 5189  # NLM VHP fact sheet figure for the female colour data set


def index_fullbody():
    section, rows = None, {}
    for line in INDEX.read_text(errors='replace').splitlines():
        if line.startswith('./') and line.endswith(':'):
            section = line[:-1]
            continue
        if section == './Fullcolor/fullbody':
            m = re.search(r'(\d+)\s+(\w+\s+\d+\s+\d{4})\s+(avf\d{4}[abc]\.raw\.Z)$', line)
            if m:
                rows[m.group(3)] = {'bytes': int(m.group(1)), 'date': m.group(2)}
    return rows


def head(url, timeout=30):
    req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'female-open-atlas origin check'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {'status': r.status, 'content_length': r.headers.get('Content-Length')}
    except urllib.error.HTTPError as e:
        return {'status': e.code, 'content_length': None}
    except Exception as e:  # noqa: BLE001
        return {'status': None, 'error': str(e)[:120]}


def groups(names):
    """Contiguous runs of (mm, sub) positions -> list of {first, last, count, thickness}."""
    order = {'a': 0, 'b': 1, 'c': 2}
    idx = sorted(int(n[3:7]) * 3 + order[n[7]] for n in names)
    runs, start = [], None
    for i, v in enumerate(idx):
        if start is None:
            start = v
        if i + 1 == len(idx) or idx[i + 1] != v + 1:
            runs.append((start, v)); start = None
    def name(v):
        return f'avf{v // 3:04d}{"abc"[v % 3]}'
    return [{'first': name(a), 'last': name(b), 'count': b - a + 1,
             'thickness_of_missing_slices_mm': round((b - a + 1) * SUB_MM, 2),
             'distance_between_bounding_valid_slices_mm': round((b - a + 2) * SUB_MM, 2)} for a, b in runs]


def main():
    inv = json.loads(INVENTORY.read_text())
    disk = {r['file']: r for r in inv['files']}
    origin = index_fullbody()
    absent_pairs = inv['summary']['missing_pairs_inside_range']
    absent = [f'avf{mm}{sub}.raw.Z' for mm, sub in absent_pairs]
    placeholders = sorted(inv['summary']['constant_or_blank'])
    size_mismatch = sorted(n for n in disk if n in origin and origin[n]['bytes'] != disk[n]['bytes'])
    probe = {}
    if '--offline' not in sys.argv:
        controls = ['avf2328b.raw.Z', 'avf2329c.raw.Z', 'avf2730b.raw.Z', 'avf1001a.raw.Z']
        for n in absent + controls:
            probe[n] = dict(head(BASE + n), expected='absent' if n in absent else 'present')
    origin_placeholders = sorted(n for n, r in origin.items() if r['bytes'] == 5454)
    usable = len(disk) - len(placeholders)
    report = {
        'purpose': 'origin completeness of the fullbody colour set, separate from the local integrity proven by inventory-cryosections.py',
        'inventory': str(INVENTORY.relative_to(ROOT)),
        'origin_listing': {'file': str(INDEX.relative_to(ROOT)), 'section': './Fullcolor/fullbody', 'listing_date': '1996-02-01 (NLM ls -lR shipped with the data set)',
                           'entries': len(origin), 'placeholders_5454_bytes': len(origin_placeholders)},
        'local_vs_origin_listing': {'in_origin_not_on_disk': sorted(set(origin) - set(disk)), 'on_disk_not_in_origin': sorted(set(disk) - set(origin)),
                                    'byte_size_mismatches': size_mismatch, 'placeholder_lists_equal': origin_placeholders == placeholders},
        'absent_inside_range': {'files': absent, 'listed_by_origin': [n for n in absent if n in origin],
                                'conclusion': 'absent from the 1996 origin listing and not served by the NLM server today (HEAD 403; neighbours 200)' if not any(n in origin for n in absent) and probe and all(probe[n]['status'] == 403 for n in absent) and all(probe[c]['status'] == 200 for c in probe if probe[c]['expected'] == 'present')
                                else 'not established (see probe and listing)'},
        'server_probe': {'base_url': BASE, 'method': 'HTTP HEAD; the server answers 403 for unserved paths and for directory listings', 'results': probe},
        'counts': {'files_on_disk': len(disk), 'expected_if_complete': inv['summary']['expected_slices_if_complete'], 'absent': len(absent),
                   'placeholders': len(placeholders), 'usable_slices': usable,
                   'nlm_documented_slice_count': NLM_DOCUMENTED_SLICES,
                   'nlm_documented_count_note': f'NLM documents {NLM_DOCUMENTED_SLICES} slices; the origin listing has {len(origin)} files and {len(origin) - len(origin_placeholders)} non-placeholder files; neither matches {NLM_DOCUMENTED_SLICES}, so the documented figure is recorded as unexplained, not attributed to any single absent file'},
        'placeholder_groups': groups([n[:8] for n in placeholders]),
        'absent_groups': groups([n[:8] for n in absent]),
        'thickness_rule': 'thickness_of_missing_slices_mm = count x 1/3 mm; distance_between_bounding_valid_slices_mm = (count + 1) x 1/3 mm; both are declared-spacing values, unverified until stage 0',
    }
    OUT.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'origin_entries': len(origin), 'in_origin_not_on_disk': len(report['local_vs_origin_listing']['in_origin_not_on_disk']),
                      'size_mismatches': len(size_mismatch), 'absent_conclusion': report['absent_inside_range']['conclusion'],
                      'probe': {k: v['status'] for k, v in probe.items()}, 'placeholder_groups': [(g['first'], g['last'], g['count']) for g in report['placeholder_groups']],
                      'usable': usable}))


if __name__ == '__main__':
    main()
