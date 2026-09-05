"""Download the NLM Visible Human Female fresh ("normal") CT series with auditable provenance.

Source: https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/radiological/
Terms: https://www.nlm.nih.gov/databases/download/terms_and_conditions.html (no licence or
registration since July 2019; attribution "Courtesy of the U.S. National Library of Medicine";
no implied NLM endorsement; redistributed derivatives must state whether they reflect the
current NLM data). Every file is recorded with URL, size and SHA-256 in `download-manifest.json`.

Usage: .venv/bin/python scripts/fetch-nlm-vhf.py [--workers 8]
Re-running skips files whose recorded SHA-256 matches the local copy.
"""
import argparse
import concurrent.futures
import hashlib
import json
import re
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/nlm-vhf'
BASE = 'https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/'
TERMS = 'https://www.nlm.nih.gov/databases/download/terms_and_conditions.html'
parser = argparse.ArgumentParser()
parser.add_argument('--workers', type=int, default=8)
args = parser.parse_args()
RAW.mkdir(parents=True, exist_ok=True)
manifest_path = RAW / 'download-manifest.json'
manifest = {r['url']: r for r in json.loads(manifest_path.read_text())} if manifest_path.exists() else {}
session = requests.Session()
session.headers['User-Agent'] = 'female-open-human-atlas/fetch-nlm-vhf (research; contact via repository)'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def fetch(url, local):
    local.parent.mkdir(parents=True, exist_ok=True)
    record = manifest.get(url)
    if record and local.exists() and local.stat().st_size == record['bytes'] and sha256(local) == record['sha256']:
        return record, False
    for attempt in range(6):
        try:
            response = session.get(url, timeout=120)
            if response.status_code == 200:
                break
            raise requests.HTTPError(f'HTTP {response.status_code} for {url}')
        except (requests.RequestException, requests.HTTPError) as error:
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)
    local.write_bytes(response.content)
    record = {'url': url, 'local': str(local.relative_to(ROOT)), 'bytes': len(response.content),
              'sha256': hashlib.sha256(response.content).hexdigest(), 'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'content_type': response.headers.get('Content-Type'), 'last_modified': response.headers.get('Last-Modified')}
    return record, True


def save():
    manifest_path.write_text(json.dumps(sorted(manifest.values(), key=lambda r: r['url']), indent=2) + '\n')


# 1. Terms, READMEs and the directory INDEX are the licence and inventory evidence.
for url, local in [(TERMS, RAW / 'terms_and_conditions.html'), (BASE + 'README', RAW / 'README'),
                   (BASE + 'radiological/normalCT/README', RAW / 'normalCT-README'), (BASE + 'INDEX', RAW / 'INDEX')]:
    record, fetched = fetch(url, local)
    manifest[url] = record
    print(('fetched ' if fetched else 'kept    ') + local.name, flush=True)
save()
terms = (RAW / 'terms_and_conditions.html').read_text(errors='replace')
assert 'Courtesy of the U.S. National Library of Medicine' in terms, 'Terms page changed; re-verify before use'
index = (RAW / 'INDEX').read_text(errors='replace')
ct_files = sorted(set(re.findall(r'(c_vf\d{4}\.fre\.Z)', index)))
header_files = sorted(set(re.findall(r'(c_vf\d{4}\.txt)', index)))
assert len(ct_files) == len(header_files) == 1734, (len(ct_files), len(header_files))
jobs = [(BASE + 'radiological/normalCT/' + name, RAW / 'normalCT' / name) for name in ct_files]
jobs += [(BASE + 'radiological/normalCTHeaders/' + name, RAW / 'normalCTHeaders' / name) for name in header_files]
done = fetched_count = 0
with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
    futures = {pool.submit(fetch, url, local): url for url, local in jobs}
    for future in concurrent.futures.as_completed(futures):
        record, fetched = future.result()
        manifest[record['url']] = record
        done += 1
        fetched_count += fetched
        if done % 100 == 0 or done == len(jobs):
            save()
            print(f'{done}/{len(jobs)} files ({fetched_count} newly fetched)', flush=True)
save()
total = sum(r['bytes'] for r in manifest.values())
print(json.dumps({'files': len(manifest), 'bytes': total, 'ct_slices': len(ct_files), 'manifest': str(manifest_path.relative_to(ROOT))}))
