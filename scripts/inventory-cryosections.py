"""Inventory of the NLM Visible Human Female colour cryosections (plan B stage 0, first step of block C).

Usage (on the box that holds the files, e.g. rub-pc):
  python3 scripts/inventory-cryosections.py /media/rub/Backups/VHF/Female-Images [--workers 12] [--out inventory.json]

Checks, all automatic, nothing anatomical:
  1. Every file listed in fullbody-sha256.txt exists, has the recorded SHA-256 and the recorded URL; extra files are listed.
  2. Naming: avfNNNN[a|b|c].raw.Z. NNNN is the millimetre position along the block (1001 = top), the letter the 0.33 mm
     sub-slice (a, b, c). Missing (number, letter) pairs inside the observed range are listed: they explain the difference
     between the files present and the 5,189 slices the NLM documentation quotes for the female data set.
  3. Each file decompresses (compress/LZW) to exactly 2048 x 1216 x 3 bytes (24-bit RGB, no header) as NLM documents for the
     female colour images; any other length is reported with its size. Byte layout verified on avf1800a (13 September 2026):
     PLANAR, three consecutive planes R, G, B of 2048 x 1216 each (interleaved and row-planar readings give identical channel
     means and a grey image; the planar reading gives the blue block, red muscle and yellow fat).
  4. Per-slice content statistics on the decompressed bytes: mean and standard deviation per channel, fraction of near-black
     pixels (blue background of the block is not black; an all-black or constant slice is a corrupt or blank file).
  5. Spacing and orientation are documentation values (0.33 mm x 0.33 mm x 0.33 mm) and are recorded as *declared,
     unverified*: the image-to-Denver comparison of stage 0 (`scripts/check-cryosection-alignment.py`) measures them.
     Measured there on 13 September 2026: columns increase towards the subject's left, rows increase towards anterior
     (Denver's aligned slices are the photographs mirrored left-right; the patella lies at larger row than the femur in
     the Denver label map), one Denver pixel = 2.000 photograph pixels, three photographs per millimetre.
Output: one JSON with per-file rows and a summary. Runtime is disk-bound (22 GB read for the hashes and again for the
decompression); with 12 workers about 10 minutes on rub-pc.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

W, H, C = 2048, 1216, 3
EXPECTED_RAW = W * H * C
NAME = re.compile(r'^avf(\d{4})([a-z]?)\.raw\.Z$')


def one(args):
    path, expected_sha = args
    p = Path(path)
    row = {'file': p.name, 'bytes': p.stat().st_size}
    m = NAME.match(p.name)
    row['mm'], row['sub'] = (int(m.group(1)), m.group(2)) if m else (None, None)
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    row['sha256'] = h.hexdigest()
    row['sha256_ok'] = (expected_sha is None) or (row['sha256'] == expected_sha)
    try:
        raw = subprocess.run(['gzip', '-dc', str(p)], capture_output=True, check=True, timeout=600).stdout
        row['raw_bytes'] = len(raw)
        row['raw_ok'] = len(raw) == EXPECTED_RAW
        if row['raw_ok']:
            import numpy as np
            a = np.frombuffer(raw, dtype=np.uint8).reshape(C, H, W).transpose(1, 2, 0)   # planar R, G, B planes
            sub = a[::8, ::8].astype(np.float32)
            row['mean_rgb'] = [round(float(x), 2) for x in sub.reshape(-1, 3).mean(axis=0)]
            row['std_rgb'] = [round(float(x), 2) for x in sub.reshape(-1, 3).std(axis=0)]
            row['near_black_fraction'] = round(float((sub.max(axis=2) < 16).mean()), 4)
            row['constant'] = bool(sub.std() < 1.0)
            # a colour image has distinct channel means; equal means would indicate a wrong layout or a grey placeholder
            row['channel_means_distinct'] = bool(max(row['mean_rgb']) - min(row['mean_rgb']) > 1.0)
    except Exception as e:  # noqa: BLE001
        row['raw_bytes'], row['raw_ok'], row['error'] = None, False, str(e)[:200]
    return row


def main():
    root = Path(sys.argv[1])
    workers = int(sys.argv[sys.argv.index('--workers') + 1]) if '--workers' in sys.argv else 12
    out = Path(sys.argv[sys.argv.index('--out') + 1]) if '--out' in sys.argv else root / 'fullbody-inventory.json'
    folder = root / 'fullbody'
    manifest = {}
    for line in (root / 'fullbody-sha256.txt').read_text().splitlines():
        if line.strip():
            sha, name = line.split()
            manifest[name.strip()] = sha
    urls = {u.rsplit('/', 1)[-1]: u for u in (root / 'fullbody-urls.txt').read_text().split()}
    present = {p.name for p in folder.iterdir() if p.is_file()}
    jobs = [(str(folder / n), manifest.get(n)) for n in sorted(present)]
    t0 = time.time()
    rows = []
    with ProcessPoolExecutor(workers) as ex:
        for i, row in enumerate(ex.map(one, jobs, chunksize=8), 1):
            row['url'] = urls.get(row['file'])
            rows.append(row)
            if i % 250 == 0:
                print(f'{i}/{len(jobs)} files, {time.time() - t0:.0f} s', flush=True)
    by_pair = {(r['mm'], r['sub']) for r in rows if r['mm'] is not None}
    mms = sorted({r['mm'] for r in rows if r['mm'] is not None})
    subs = sorted({r['sub'] for r in rows if r['sub'] is not None})
    missing_pairs = [[mm, s] for mm in range(mms[0], mms[-1] + 1) for s in subs if (mm, s) not in by_pair] if mms else []
    summary = {
        'folder': str(folder), 'files_present': len(present), 'files_in_manifest': len(manifest),
        'missing_from_disk': sorted(set(manifest) - present), 'not_in_manifest': sorted(present - set(manifest)),
        'sha256_mismatch': sorted(r['file'] for r in rows if not r['sha256_ok']),
        'raw_size_mismatch': sorted((r['file'], r['raw_bytes']) for r in rows if not r['raw_ok']),
        'constant_or_blank': sorted(r['file'] for r in rows if r.get('constant')),
        'unparsed_names': sorted(r['file'] for r in rows if r['mm'] is None),
        'mm_range': [mms[0], mms[-1]] if mms else None, 'mm_positions': len(mms), 'sub_slices': subs,
        'files_per_sub_slice': {s: sum(1 for r in rows if r['sub'] == s) for s in subs},
        'missing_pairs_inside_range': missing_pairs,
        'expected_slices_if_complete': (mms[-1] - mms[0] + 1) * len(subs) if mms else None,
        'nlm_documented_slice_count': 5189,
        'grey_or_equal_channel_slices': sorted(r['file'] for r in rows if r.get('raw_ok') and not r.get('constant') and not r.get('channel_means_distinct')),
        'byte_layout': 'planar: R plane, G plane, B plane, each 1216 rows x 2048 columns (verified visually on avf1800a)',
        'declared_geometry_unverified': {'width_px': W, 'height_px': H, 'channels': C, 'pixel_mm': 0.33, 'slice_mm': 0.33,
                                         'note': 'from the NLM Visible Human Project documentation for the female colour images; verified here only through the decompressed byte count; spacing and orientation are verified in stage 0 against Denver aligned slices, not here'},
        'total_bytes': sum(r['bytes'] for r in rows), 'seconds': round(time.time() - t0, 1),
    }
    out.write_text(json.dumps({'summary': summary, 'files': rows}, indent=1) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('missing_pairs_inside_range',)} | {'missing_pairs_inside_range': missing_pairs[:20], 'missing_pairs_count': len(missing_pairs)}))
    print('INVENTORY_DONE')


if __name__ == '__main__':
    main()
