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
    parser.add_argument('--benchmark',action='store_true')
    parser.add_argument('--base-url',default='http://127.0.0.1:3017')
    parser.add_argument('--production',action='store_true',help='Skip source-module numeric checks; run UI/recovery/optional benchmark against the built app')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'errors': [], 'viewports': [], 'baseUrl': args.base_url, 'production': args.production}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.executable, headless=True,
                                   env={k:v for k,v in os.environ.items() if k not in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']},
                                   args=['--no-sandbox','--use-gl=angle','--use-angle=swiftshader-webgl','--enable-unsafe-swiftshader'])
        report['browser'] = browser.version
        page = browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror', lambda e: report['errors'].append(str(e)))
        page.on('console', lambda m: report['errors'].append(m.text) if ('texSubImage' in m.text or 'GL_INVALID' in m.text) else None)
        page.goto(args.base_url)
        if not args.production:
            report['phantom'] = page.evaluate('''async root=>{
              const {checkShaderPhantom}=await import(root+'/scripts/slices-shader-checks.mjs');return checkShaderPhantom();
            }''','/@fs'+str(ROOT))
            # This oracle path imports the tested source modules from Vite. No production debug hook.
            report['gpu'] = page.evaluate('''async root=>{
              const {VolumeLoader}=await import(root+'/app/slices/volume-loader.ts');
              const {SliceRenderEngine}=await import(root+'/app/slices/render-engine.ts');
              const C=await import(root+'/app/slices/coordinates.ts');
              const {sampleStage}=await import(root+'/app/slices/sampler.ts');
              const volume=await new VolumeLoader().load(location.origin+'/volumes/nlm-abdomen/manifest.json');
              const engine=new SliceRenderEngine(volume,message=>{throw Error(message)});
              let maximumError=0,compared=0,supportMismatches=0,labelMismatches=0;const mismatches=[];
              const center=C.transform(volume.voxelToStage,[85,90,51]);
              const axial=C.orthogonalPlane(volume.voxelToStage,center,'axial');
              const planes=[axial,C.orthogonalPlane(volume.voxelToStage,center,'coronal'),C.orthogonalPlane(volume.voxelToStage,center,'sagittal'),C.obliquePlane(axial,23,-47),C.obliquePlane(axial,-61,31)];
              for(const plane of planes){
                const width=64,height=64,mpp=.0037,values=engine.readSamples(plane,width,height,mpp);
                for(let y=0;y<height;y++)for(let x=0;x<width;x++){
                  const cpu=sampleStage(volume,C.pixelPoint(plane,x,y,width,height,mpp));
                  const offset=((height-1-y)*width+x)*4,valid=values[offset+2]>.5;
                  if((cpu.state==='acquired')!==valid){supportMismatches++;if(mismatches.length<5)mismatches.push({p:C.transform(volume.stageToVoxel,C.pixelPoint(plane,x,y,width,height,mpp)),cpu,gpu:Array.from(values.slice(offset,offset+4))});continue;}
                  if(valid){maximumError=Math.max(maximumError,Math.abs(cpu.hu-values[offset]));if(cpu.label!==values[offset+1])labelMismatches++;compared++;}
                }
              }
              const gl=engine.renderer.getContext(),extension=gl.getExtension('WEBGL_debug_renderer_info');
              const renderer=extension?gl.getParameter(extension.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
              engine.dispose();
              if(maximumError>.1||supportMismatches||labelMismatches||compared<1000)throw Error(JSON.stringify({maximumError,supportMismatches,labelMismatches,compared,mismatches}));
              return {maximumError,supportMismatches,labelMismatches,compared,renderer,volumeBytes:volume.intensity.byteLength+volume.labels.byteLength+volume.support.byteLength};
            }''','/@fs'+str(ROOT))
        for width,height in [(1440,1000),(390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            page.get_by_role('button',name='Open Slices',exact=True).click()
            page.locator('.slice-image canvas').first.wait_for(timeout=60000)
            page.wait_for_timeout(1500)
            assert not page.get_by_role('alert').count()
            axial=page.get_by_label('Axial image navigation',exact=True)
            rect=axial.bounding_box()
            click={'x':rect['width']*.57,'y':rect['height']*.48}
            axial.click(position=click);page.wait_for_timeout(150)
            picked=page.locator('.slices-footer').inner_text()
            axial.click(position=click);page.wait_for_timeout(150)
            assert picked==page.locator('.slices-footer').inner_text(), 'Repeated pixel pick accumulated motion'
            page.locator('.slices-controls').hover();page.mouse.wheel(0,90);page.wait_for_timeout(100)
            assert picked==page.locator('.slices-footer').inner_text(), 'Sidebar wheel moved a slice'
            if width>650:
                scene=page.locator('.slice-three-host canvas').bounding_box()
                page.get_by_label('Slice structure',exact=True).select_option('1')
                page.wait_for_timeout(150)
                before_image=page.locator('[data-slice=axial] canvas').screenshot()
                before_3d=page.get_by_label('Slice structure',exact=True).input_value()
                page.mouse.click(scene['x']+scene['width']*.5,scene['y']+scene['height']*.5);page.wait_for_timeout(150)
                assert page.get_by_label('Slice structure',exact=True).input_value()!=before_3d, '3D organ pick did not select a mapped structure'
                page.get_by_label('Slice structure',exact=True).select_option('1')
                picked=page.locator('.slices-footer').inner_text()
                page.mouse.move(scene['x']+scene['width']*.5,scene['y']+scene['height']*.5)
                page.mouse.down();page.mouse.move(scene['x']+scene['width']*.7,scene['y']+scene['height']*.5,steps=10);page.mouse.up();page.wait_for_timeout(300)
                assert picked==page.locator('.slices-footer').inner_text(), 'Orbit moved crosshair'
                assert before_image==page.locator('[data-slice=axial] canvas').screenshot(), 'Orbit changed sampling'
            before=page.locator('.slices-footer').inner_text()
            page.get_by_label('Slice structure',exact=True).select_option('1')
            after=page.locator('.slices-footer').inner_text()
            assert before.split('stage ')[1]==after.split('stage ')[1], 'Selection moved crosshair'
            axial=page.get_by_label('Axial image navigation',exact=True)
            point_before=page.locator('.slices-footer').inner_text()
            axial.focus();axial.press('ArrowUp')
            assert point_before!=page.locator('.slices-footer').inner_text(), 'Keyboard did not move slice'
            page.get_by_role('button',name='Center on structure',exact=True).click()
            assert after!=page.locator('.slices-footer').inner_text()
            # Label-pixel selection reports the sampled label (or an explicit
            # unsupported-coverage state) without inventing a structure.
            page.get_by_label('Click action',exact=True).select_option('select')
            rect=axial.bounding_box();axial.click(position={'x':rect['width']*.5,'y':rect['height']*.5});page.wait_for_timeout(100)
            assert page.locator('[data-slice=axial] header span').inner_text().startswith(('HU ','Outside supported coverage'))
            page.get_by_label('Click action',exact=True).select_option('navigate')
            # Shift-drag pans the image while leaving the shared physical point
            # unchanged; plane visibility and mask fill are independent toggles.
            point_before=page.locator('.slices-footer').inner_text();before_image=page.locator('[data-slice=axial] canvas').screenshot()
            rect=axial.bounding_box();page.mouse.move(rect['x']+rect['width']*.4,rect['y']+rect['height']*.5);page.keyboard.down('Shift');page.mouse.down();page.mouse.move(rect['x']+rect['width']*.55,rect['y']+rect['height']*.5,steps=3);page.mouse.up();page.keyboard.up('Shift');page.wait_for_timeout(120)
            assert point_before==page.locator('.slices-footer').inner_text(), 'Panning moved the shared point'
            assert before_image!=page.locator('[data-slice=axial] canvas').screenshot(), 'Pan did not move the image'
            page.get_by_label('Fill mask',exact=True).check()
            page.get_by_label('Show planes in 3D',exact=True).uncheck()
            page.get_by_label('Show planes in 3D',exact=True).check()
            if width<650:
                page.get_by_label('Active slice',exact=True).select_option('coronal')
                assert page.locator('.slice-grid').get_attribute('data-active')=='coronal'
            wheel_panel=axial if width>650 else page.get_by_label('Coronal image navigation',exact=True)
            wheel_panel.hover();page.mouse.wheel(0,100);page.wait_for_timeout(150)
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
            if 'load' not in report:
                report['load']=page.evaluate('''()=>{
                  const entries=performance.getEntriesByType('resource').filter(e=>e.name.includes('/volumes/nlm-abdomen/')||e.name.includes('/models/nlm-vhf-ct-lod-'));
                  return {resources:entries.length,transferBytes:entries.reduce((n,e)=>n+(e.transferSize||0),0),decodedBytes:entries.reduce((n,e)=>n+(e.decodedBodySize||0),0),maxResourceDurationMs:entries.reduce((n,e)=>Math.max(n,e.duration),0),entries:entries.map(e=>({name:e.name.split('/').pop(),transferBytes:e.transferSize||0,decodedBytes:e.decodedBodySize||0,durationMs:e.duration}))};
                }''')
            page.get_by_role('button',name='Atlas',exact=True).click()
            assert page.get_by_label('Anatomical reference',exact=True).input_value()=='hra-female'
        assert not report['errors'], report['errors']
        # Visible loading failure and retry, using a missing volume chunk rather than malformed UI state.
        page.route('**/volumes/nlm-abdomen/intensity-*.bin',lambda route:route.fulfill(status=404,body='missing'))
        page.get_by_role('button',name='Open Slices',exact=True).click()
        page.get_by_role('alert').wait_for(timeout=60000)
        assert 'missing asset' in page.get_by_role('alert').inner_text()
        page.unroute('**/volumes/nlm-abdomen/intensity-*.bin')
        page.get_by_role('button',name='Retry preview',exact=True).click()
        page.locator('.slice-image canvas').first.wait_for(timeout=60000)
        page.wait_for_timeout(500)
        # A real context-loss event must present recovery rather than leave stale images interactive.
        page.locator('.slice-three-host canvas').evaluate("c=>c.getContext('webgl2').getExtension('WEBGL_lose_context').loseContext()")
        page.get_by_role('alert').wait_for(timeout=10000)
        assert '3D session' in page.get_by_role('alert').inner_text()
        page.get_by_role('button',name='Retry preview',exact=True).click()
        page.locator('.slice-image canvas').first.wait_for(timeout=60000)
        page.get_by_role('button',name='Atlas',exact=True).click()
        report['errorRecovery'] = ['missing intensity chunk → explicit error → retry','3D context loss → explicit error → retry']
        if args.benchmark:
            page.set_viewport_size({'width':1440,'height':1000})
            page.get_by_role('button',name='Open Slices',exact=True).click()
            page.locator('.slice-image canvas').first.wait_for(timeout=60000)
            page.wait_for_timeout(1000)
            report['performance'] = []
            for resolution in [384,192]:
                page.get_by_label('Display resolution',exact=True).select_option(str(resolution))
                page.wait_for_timeout(300)
                result=page.evaluate('''async()=>{
                  const samples=[];
                  const observer=new PerformanceObserver(list=>{for(const entry of list.getEntries())if(entry.name==='slices-input-to-display')samples.push({start:entry.startTime,ms:entry.duration});});
                  observer.observe({entryTypes:['measure']});
                  const image=document.querySelector('[data-slice=axial] .slice-image'),rect=image.getBoundingClientRect();
                  const event=(type,x,y)=>image.dispatchEvent(new PointerEvent(type,{bubbles:true,pointerId:1,buttons:type==='pointerup'?0:1,clientX:rect.x+x*rect.width,clientY:rect.y+y*rect.height}));
                  // A real pointer owns capture before synthetic continuous moves are generated.
                  const original=image.setPointerCapture;image.setPointerCapture=()=>{};
                  event('pointerdown',.5,.5);
                  for(let frame=0;frame<120;frame++){await new Promise(requestAnimationFrame);event('pointermove',.5+.04*Math.sin(frame/10),.5+.03*Math.cos(frame/10));}
                  event('pointerup',.5,.5);image.setPointerCapture=original;
                  for(let frame=0;frame<5;frame++)await new Promise(requestAnimationFrame);
                  observer.disconnect();
                  const steady=samples.slice(5),durations=steady.map(s=>s.ms).sort((a,b)=>a-b);
                  if(steady.length<10)throw Error('Insufficient complete-frame timing samples: '+samples.length);
                  const p95=durations[Math.floor((durations.length-1)*.95)],fps=(steady.length-1)*1000/(steady.at(-1).start-steady[0].start);
                  return {samples:samples.length,p95Ms:p95,fps,meetsTarget:p95<100&&fps>=30,timelineEntriesRetained:performance.getEntriesByName('slices-input-to-display').length};
                }''')
                report['performance'].append({'resolution':resolution,**result})
            cdp=page.context.new_cdp_session(page)
            report['retainedHeap'] = []
            for cycle in range(8):
                page.get_by_role('button',name='Atlas',exact=True).click()
                page.get_by_role('button',name='Open Slices',exact=True).click()
                page.locator('.slice-image canvas').first.wait_for(timeout=60000)
                page.wait_for_timeout(500)
                cdp.send('HeapProfiler.collectGarbage')
                report['retainedHeap'].append(cdp.send('Runtime.getHeapUsage'))
            page.get_by_role('button',name='Atlas',exact=True).click()
        browser.close()
    (OUT/('browser-production-report.json' if args.production else 'browser-report.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    run()
