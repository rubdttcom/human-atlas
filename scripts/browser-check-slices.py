"""Slices functional and GPU-reference checks against the local Vite server (port 3017).

Uses an existing Playwright Chromium executable; no downloads. Headless tests must
not inherit DISPLAY: ANGLE otherwise tries the user's authenticated X11 session.
"""
import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/slices'


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', default=str(Path.home()/'.cache/ms-playwright/chromium_headless_shell-1200/chrome-headless-shell-linux64/chrome-headless-shell'))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'errors': [], 'viewports': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.executable, headless=True,
                                   env={k:v for k,v in os.environ.items() if k not in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']},
                                   args=['--no-sandbox','--use-gl=angle','--use-angle=swiftshader-webgl','--enable-unsafe-swiftshader'])
        report['browser'] = browser.version
        page = browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror', lambda e: report['errors'].append(str(e)))
        page.goto('http://127.0.0.1:3017')
        # This oracle path imports the tested source modules from Vite. No production debug hook.
        report['gpu'] = page.evaluate('''async root=>{
          const {VolumeLoader}=await import(root+'/app/slices/volume-loader.ts');
          const {SliceRenderEngine}=await import(root+'/app/slices/render-engine.ts');
          const C=await import(root+'/app/slices/coordinates.ts');
          const {sampleStage}=await import(root+'/app/slices/sampler.ts');
          const volume=await new VolumeLoader().load(location.origin+'/volumes/nlm-abdomen/manifest.json');
          const engine=new SliceRenderEngine(volume,message=>{throw Error(message)});
          let maximumError=0,compared=0,supportMismatches=0,labelMismatches=0;
          const center=C.transform(volume.voxelToStage,[85,90,51]);
          const axial=C.orthogonalPlane(volume.voxelToStage,center,'axial');
          const planes=[axial,C.orthogonalPlane(volume.voxelToStage,center,'coronal'),C.orthogonalPlane(volume.voxelToStage,center,'sagittal'),C.obliquePlane(axial,23,-47),C.obliquePlane(axial,-61,31)];
          for(const plane of planes){
            const width=64,height=64,mpp=.0037,values=engine.readSamples(plane,width,height,mpp);
            for(let y=0;y<height;y++)for(let x=0;x<width;x++){
              const cpu=sampleStage(volume,C.pixelPoint(plane,x,y,width,height,mpp));
              const offset=((height-1-y)*width+x)*4,valid=values[offset+2]>.5;
              if((cpu.state==='acquired')!==valid){supportMismatches++;continue;}
              if(valid){maximumError=Math.max(maximumError,Math.abs(cpu.hu-values[offset]));if(cpu.label!==values[offset+1])labelMismatches++;compared++;}
            }
          }
          const gl=engine.renderer.getContext(),extension=gl.getExtension('WEBGL_debug_renderer_info');
          const renderer=extension?gl.getParameter(extension.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
          engine.dispose();
          if(maximumError>.1||supportMismatches||labelMismatches||compared<1000)throw Error(JSON.stringify({maximumError,supportMismatches,labelMismatches,compared}));
          return {maximumError,supportMismatches,labelMismatches,compared,renderer,volumeBytes:volume.intensity.byteLength+volume.labels.byteLength+volume.support.byteLength};
        }''','/@fs'+str(ROOT))
        for width,height in [(1440,1000),(390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            page.get_by_role('button',name='Open Slices',exact=True).click()
            page.locator('.slice-image canvas').first.wait_for(timeout=60000)
            page.wait_for_timeout(1500)
            assert not page.get_by_role('alert').count()
            before=page.locator('.slices-footer').inner_text()
            page.get_by_label('Slice structure',exact=True).select_option('1')
            after=page.locator('.slices-footer').inner_text()
            assert before.split('stage ')[1]==after.split('stage ')[1], 'Selection moved crosshair'
            page.get_by_role('button',name='Center on structure',exact=True).click()
            assert after!=page.locator('.slices-footer').inner_text()
            axial=page.get_by_label('Axial image navigation',exact=True)
            point_before=page.locator('.slices-footer').inner_text()
            axial.focus();axial.press('ArrowUp')
            assert point_before!=page.locator('.slices-footer').inner_text(), 'Keyboard did not move slice'
            axial.hover();page.mouse.wheel(0,100);page.wait_for_timeout(150)
            page.get_by_role('button',name='Oblique',exact=True).click()
            assert page.locator('[data-slice=oblique]').count()==1
            point_before=page.locator('.slices-footer').inner_text()
            page.get_by_label('Initial right angle',exact=True).fill('23')
            assert point_before==page.locator('.slices-footer').inner_text(), 'Rotation moved pivot'
            page.get_by_label('Initial up angle',exact=True).fill('-47')
            page.get_by_label('Window width',exact=True).fill('0')
            assert float(page.get_by_label('Window width',exact=True).input_value())>0
            page.get_by_role('button',name='Soft tissue',exact=True).click()
            page.get_by_role('button',name='Reset orientation',exact=True).click()
            assert page.get_by_label('Initial right angle',exact=True).input_value()=='0'
            page.get_by_label('Display resolution',exact=True).select_option('192')
            page.wait_for_timeout(500)
            stats=page.locator('[data-slice=oblique] canvas').evaluate('''c=>{
              const data=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let tissue=0;
              for(let i=0;i<data.length;i+=4)if(data[i]>50&&data[i+1]>50&&data[i+2]>50)tissue++;
              return {tissue,width:c.width,height:c.height};}''')
            assert stats['tissue']>100, 'No CT tissue rendered'
            assert stats['width']<=192
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Horizontal overflow'
            page.screenshot(path=str(OUT/f'{width}x{height}.png'))
            report['viewports'].append({'width':width,'height':height,'image':stats})
            page.get_by_role('button',name='Atlas',exact=True).click()
            assert page.get_by_label('Anatomical reference',exact=True).input_value()=='hra-female'
        assert not report['errors'], report['errors']
        browser.close()
    (OUT/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    run()
