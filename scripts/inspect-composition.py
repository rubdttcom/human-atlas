"""Capture the revised composite independently of the source-atlas browser suite."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/browser'
OUT.mkdir(parents=True, exist_ok=True)
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True,
                                args=['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    for width, height in [(1440, 1000), (390, 844), (320, 568), (844, 390)]:
        page = browser.new_page(viewport={'width': width, 'height': height}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:3017/?source=composed', wait_until='networkidle', timeout=60000)
        page.locator('.loading[role="status"]').wait_for(state='hidden', timeout=60000)
        page.wait_for_timeout(600)
        assert page.locator('.registration-note').is_visible()
        assert page.get_by_label('Anatomical reference').input_value() == 'composed'
        filename = OUT / f'{width}x{height}-composed-regional.png'
        page.screenshot(path=str(filename))
        pixels = np.asarray(Image.open(filename).convert('RGB')).astype(int)
        # Exclude the source warning and side panels from this anatomy pixel check.
        region = pixels[210:height-160, width//3:2*width//3] if height > width else pixels[110:height-120, width//3:2*width//3]
        colored = int(np.count_nonzero(region.max(axis=2) - region.min(axis=2) > 24))
        assert colored > 150, colored
        assert not errors, errors
        results.append({'viewport': [width, height], 'anatomy_colored_pixels': colored, 'page_errors': errors})
        page.close()
    browser.close()
(OUT / 'composition-results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
