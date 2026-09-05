"""Fetch one public TCIA segmentation and its key with validated ZIP CRCs."""
import hashlib
import json
from pathlib import Path
from remotezip import RemoteZip
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/raw/tcia'
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'https://www.cancerimagingarchive.net/wp-content/uploads/'
URL = BASE + 'Healthy-Total-Body-CTs-NIfTI-Segmentations-and-Segmentation-Organ-Values-spreadsheet.zip'
records = []
with RemoteZip(URL, timeout=60) as archive:
    names = archive.namelist()
    print(json.dumps(names, indent=2), flush=True)
    selected = [name for name in names if not name.startswith('__MACOSX/') and
                (name.lower().endswith(('.xlsx', '.csv')) or ('003' in name and name.endswith(('.nii', '.nii.gz'))))]
    assert any('003' in name for name in selected), 'Subject 003 not found'
    for name in selected:
        data = archive.read(name)
        target = OUT / Path(name).name
        target.write_bytes(data)
        records.append({'url': URL, 'archive_member': name, 'local': str(target.relative_to(ROOT)),
                        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                        'archive_crc32': archive.getinfo(name).CRC})
        print(f'Fetched {name}: {len(data)} bytes', flush=True)
url = BASE + 'Healthy-Total-Body-CTs_v02_20240927.xlsx'
response = requests.get(url, timeout=60)
response.raise_for_status()
target = OUT / 'demographics.xlsx'
target.write_bytes(response.content)
records.append({'url': url, 'local': str(target.relative_to(ROOT)), 'sha256': hashlib.sha256(response.content).hexdigest()})
(OUT / 'download-manifest.json').write_text(json.dumps(records, indent=2) + '\n')
