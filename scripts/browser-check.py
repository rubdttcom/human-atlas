"""Exercise the real WebGL viewer on desktop and touch-sized viewports."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/browser'
OUT.mkdir(parents=True, exist_ok=True)
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True,
                                args=['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    for width, height in [(1440, 1000), (390, 844), (320, 568), (844, 390)]:
        page = browser.new_page(viewport={'width': width, 'height': height}, device_scale_factor=1)
        print(f'Checking {width}x{height}', flush=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script('''const original = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function(type, options) {
          return original.call(this,type,type.startsWith('webgl')?{...options,preserveDrawingBuffer:true}:options);
        };''')
        page.goto('http://127.0.0.1:3017', wait_until='networkidle', timeout=60000)
        page.locator('.loading[role="status"]').wait_for(state='hidden', timeout=60000)
        page.wait_for_timeout(1000)
        canvas = page.locator('.scene canvas')
        stats = canvas.evaluate('''c=>{const s=document.createElement('canvas');s.width=c.width;s.height=c.height;
        const ctx=s.getContext('2d');ctx.drawImage(c,0,0);const a=ctx.getImageData(0,0,s.width,s.height).data;
        let colored=0,dark=0;for(let i=0;i<a.length;i+=4){if(Math.max(a[i],a[i+1],a[i+2])-Math.min(a[i],a[i+1],a[i+2])>24)colored++;if(a[i]+a[i+1]+a[i+2]<300)dark++;}
        return {colored,dark,width:c.width,height:c.height};}''')
        assert stats['colored'] > 1000, stats
        page.screenshot(path=str(OUT / f'{width}x{height}-female.png'))
        before = canvas.screenshot()
        page.get_by_role('button', name='Rotate body', exact=True).click()
        page.wait_for_timeout(1200)
        after = canvas.screenshot()
        assert before != after, 'Rotation did not change canvas'
        page.get_by_role('button', name='Pause rotation', exact=True).click()
        page.get_by_role('button', name='Search anatomy', exact=True).click()
        page.get_by_role('combobox').fill('uterus')
        page.get_by_role('option').first.click()
        page.locator('.detail-sheet').wait_for()
        # Search can select a compound concept; select a member to inspect its own provenance.
        if page.locator('.member-list button').count():
            page.locator('.member-list button').first.click()
        page.get_by_role('heading', name='Provenance', exact=True).wait_for()
        assert 'hra-female-assembly' in page.locator('.provenance').inner_text()
        page.get_by_role('button', name='Isolate structure').click()
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / f'{width}x{height}-provenance.png'))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Horizontal overflow'
        page.get_by_role('button', name='Clear selection', exact=True).click()
        page.get_by_label('Anatomical reference').select_option('bodyparts3d')
        # The previous atlas stays on screen until the new catalogue arrives; poll the header text
        # instead of racing the loading indicator.
        page.wait_for_function("document.querySelector('.identity-meta')?.innerText.includes('BodyParts3D')", timeout=60000)
        page.locator('.loading[role="status"]').wait_for(state='hidden', timeout=60000)
        if width in (1440, 390):
            for source in ('tcia', 'denver-vhf', 'composed'):
                page.get_by_label('Anatomical reference').select_option(source)
                page.locator('.loading[role="status"]').wait_for(state='hidden', timeout=60000)
                page.wait_for_timeout(700)
                page.screenshot(path=str(OUT / f'{width}x{height}-{source}.png'))
                if source == 'composed':
                    assert page.locator('.registration-note').is_visible()
            page.get_by_role('button', name='Coverage', exact=True).click()
            page.get_by_label('Coverage category').select_option('segmented')
            page.get_by_label('Search coverage').fill('Skull')
            page.locator('.coverage-table button').first.click()
            page.locator('.loading[role="status"]').wait_for(state='hidden', timeout=60000)
            page.get_by_role('heading', name='Skull', exact=True).wait_for()
            assert 'Healthy-Total-Body-CTs-003' in page.locator('.provenance').inner_text()
        assert not errors, errors
        results.append({'viewport': [width, height], 'canvas': stats, 'page_errors': errors,
                        'rotation': True, 'uterus_inspection': True, 'provenance': True, 'source_switch': True})
        page.close()
    browser.close()
(OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
