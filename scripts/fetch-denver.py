"""Fetch the Denver Visible Human Female assets through a real browser session.

The Digital Commons endpoint sits behind a Cloudflare JavaScript challenge, so
plain HTTP clients receive an HTML interstitial (or HTTP 403). A local Chrome
window resolves the challenge, then the same session downloads the selected
assets. Every file is recorded with its URL, size and SHA-256.
"""
import base64
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/raw/denver'
OUT.mkdir(parents=True, exist_ok=True)
LANDING = 'https://digitalcommons.du.edu/visiblehuman/1/'
ASSETS = {  # filename index on the record page -> local name
    '3': 'final-stl-models.zip',   # "Final 3D STL Models" (87.8 MB)
    '11': 'metadata.zip',          # "Metadata"
}
if len(sys.argv) > 1:
    ASSETS = {k: v for k, v in ASSETS.items() if k in sys.argv[1:]}
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=False,
                                args=['--no-sandbox', '--window-size=1200,900'])
    context = browser.new_context(accept_downloads=True, viewport={'width': 1200, 'height': 900})
    page = context.new_page()
    page.goto(LANDING, wait_until='domcontentloaded')
    for _ in range(60):
        if 'Just a moment' not in page.title():
            break
        time.sleep(1)
    else:
        raise SystemExit('Cloudflare challenge did not clear within 60 s')
    html = page.content()
    (OUT / 'landing-visiblehuman-1.html').write_text(html)
    title = re.search(r'<title>(.*?)</title>', html, re.S).group(1).strip()
    print('Landing:', title, flush=True)
    links = {}
    for m in re.finditer(r'href="(https://digitalcommons\.du\.edu/cgi/viewcontent\.cgi\?filename=(\d+)&amp;article=(\d+)&amp;context=visiblehuman&amp;type=additional)"[^>]*title="Download ([^"]+)"', html):
        links[m.group(2)] = {'url': m.group(1).replace('&amp;', '&'), 'article': m.group(3), 'label': m.group(4)}
    print(json.dumps(links, indent=1), flush=True)
    manifest = OUT / 'download-manifest.json'
    records = json.loads(manifest.read_text()) if manifest.exists() else []
    records = [r for r in records if r.get('filename_index') not in ASSETS]
    for index, local in ASSETS.items():
        link = links[index]
        print(f'Downloading {link["label"]} -> {local}', flush=True)
        # Fetch from inside the challenged page: the clearance cookie is bound to the
        # browser fingerprint, so out-of-page HTTP clients still receive HTTP 403.
        result = page.evaluate('''async url => {
            const response = await fetch(url, {credentials: 'include'});
            const buffer = new Uint8Array(await response.arrayBuffer());
            let binary = '';
            for (let i = 0; i < buffer.length; i += 0x8000)
              binary += String.fromCharCode.apply(null, buffer.subarray(i, i + 0x8000));
            return {status: response.status, type: response.headers.get('content-type'),
                    disposition: response.headers.get('content-disposition'), base64: btoa(binary)};
        }''', link['url'])
        assert result['status'] == 200, f'{link["url"]} -> HTTP {result["status"]}'
        data = base64.b64decode(result['base64'])
        disposition = result['disposition'] or ''
        content_type = result['type']
        target = OUT / local
        target.write_bytes(data)
        records.append({'filename_index': index, 'url': link['url'], 'label': link['label'],
                        'content_type': content_type, 'content_disposition': disposition,
                        'local': str(target.relative_to(ROOT)), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                        'fetched_via': 'google-chrome via Playwright; Cloudflare challenge resolved in-browser',
                        'landing': LANDING, 'record_title': title})
        print(f'  {len(data)} bytes, {content_type}, sha256 {records[-1]["sha256"]}', flush=True)
    browser.close()
records.sort(key=lambda r: int(r['filename_index']))
manifest.write_text(json.dumps(records, indent=2) + '\n')
print('Wrote', manifest)
