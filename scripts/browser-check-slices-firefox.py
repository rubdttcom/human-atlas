"""Firefox checks via W3C WebDriver using only the Python standard library.

Requires a local geckodriver (--driver), system Firefox, and Vite on port 3017.
Forces software Mesa/WebRender; refuses a renderer that does not identify as software.
"""
import argparse
import base64
import json
import os
import select
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/slices'


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver',default='/tmp/geckodriver')
    parser.add_argument('--base-url',default='http://127.0.0.1:3017')
    parser.add_argument('--xvfb',default='/tmp/slices-xvfb/usr/bin/Xvfb')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    def request(method,path,data=None):
        req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=90) as response:
                result=json.load(response)['value']
        except urllib.error.HTTPError as error:
            raise RuntimeError(error.read().decode()) from error
        return result
    environment={k:v for k,v in os.environ.items() if k not in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']}
    environment['LIBGL_ALWAYS_SOFTWARE']='1'
    session=None
    with (OUT/'firefox-driver.log').open('w') as log:
        display=subprocess.Popen([args.xvfb,'-displayfd','1','-screen','0','1440x1000x24','-nolisten','tcp'],stdout=subprocess.PIPE,stderr=log,env=environment)
        if not select.select([display.stdout],[],[],10)[0]:
            display.terminate();display.wait();raise RuntimeError('Xvfb did not announce a display')
        display_number=display.stdout.readline().decode().strip()
        if not display_number.isdigit():
            display.wait();raise RuntimeError('Xvfb failed; see log')
        environment['DISPLAY']=':'+display_number
        environment['GDK_BACKEND']='x11'
        process=subprocess.Popen([args.driver,'--port',str(port),'--host','127.0.0.1'],env=environment,stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if process.poll() is not None:raise RuntimeError('geckodriver exited; see log')
                try:
                    request('GET','/status');break
                except urllib.error.URLError:time.sleep(.05)
            result=request('POST','/session',{'capabilities':{'alwaysMatch':{'browserName':'firefox','moz:firefoxOptions':{
                'binary':'/usr/bin/firefox','args':[], 'prefs':{'gfx.webrender.software':True,'layers.acceleration.disabled':True,'webgl.force-enabled':True,'media.hardware-video-decoding.enabled':False}}}}})
            session=result['sessionId'];prefix='/session/'+session
            request('POST',prefix+'/timeouts',{'script':60000,'pageLoad':60000})
            def js(script,*values):return request('POST',prefix+'/execute/sync',{'script':script,'args':list(values)})
            def async_js(script,*values):return request('POST',prefix+'/execute/async',{'script':script,'args':list(values)})
            def wait_for(expression,seconds=60):
                deadline=time.monotonic()+seconds
                while time.monotonic()<deadline:
                    result=js('return '+expression)
                    if result:return result
                    time.sleep(.1)
                raise AssertionError('Timed out: '+expression+'\n'+str(js('return document.body.innerText')))
            renderer=js("const gl=document.createElement('canvas').getContext('webgl2');if(!gl)return 'NO WEBGL';const e=gl.getExtension('WEBGL_debug_renderer_info');return e?gl.getParameter(e.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER)")
            assert any(name in renderer.lower() for name in ['llvmpipe','softpipe','software','swiftshader']),renderer
            report={'version':result['capabilities']['browserVersion'],'renderer':renderer,'viewports':[]}
            request('POST',prefix+'/url',{'url':args.base_url})
            wait_for("!!document.querySelector('[aria-label=\"Open Slices\"]')")
            if args.base_url.endswith(':3017'):
                report['phantom']=async_js("const done=arguments[arguments.length-1];import(arguments[0]+'/scripts/slices-shader-checks.mjs').then(m=>m.checkShaderPhantom()).then(done,e=>done({error:String(e)}));",'/@fs'+str(ROOT))
                assert 'error' not in report['phantom'],report['phantom']
            for width,height in [(1440,1000),(390,844)]:
                request('POST',prefix+'/window/rect',{'width':width,'height':height})
                js("document.querySelector('[aria-label=\"Open Slices\"]').click()")
                wait_for("!!document.querySelector('.slice-image canvas')")
                wait_for("document.querySelector('[data-slice=axial] canvas').width>32")
                before=js("return document.querySelector('.slices-footer').innerText")
                js("const el=document.querySelector('[aria-label=\"Slice structure\"]');el.value='1';el.dispatchEvent(new Event('change',{bubbles:true}))")
                after=js("return document.querySelector('.slices-footer').innerText")
                assert before.split('stage ')[1]==after.split('stage ')[1]
                def button(text):js("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===arguments[0]).click()",text)
                button('Center on structure')
                assert after!=js("return document.querySelector('.slices-footer').innerText")
                button('Oblique')
                wait_for("!!document.querySelector('[data-slice=oblique] canvas')")
                js("const el=document.querySelector('[aria-label=\"Initial right angle\"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'23');el.dispatchEvent(new Event('input',{bubbles:true}))")
                time.sleep(.2)
                assert js("return document.querySelector('[aria-label=\"Initial right angle\"]').value")=='23'
                button('Reset orientation')
                assert js("return document.querySelector('[aria-label=\"Initial right angle\"]').value")=='0'
                pixels=wait_for("(()=>{const c=document.querySelector('[data-slice=oblique] canvas');const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let tissue=0;for(let i=0;i<a.length;i+=4)if(a[i]>50&&a[i+1]>50&&a[i+2]>50)tissue++;return tissue>100?tissue:0})()")
                assert js('return document.documentElement.scrollWidth<=innerWidth')
                screenshot=request('GET',prefix+'/screenshot')
                (OUT/f'firefox-{width}x{height}.png').write_bytes(base64.b64decode(screenshot))
                report['viewports'].append({'width':width,'height':height,'tissuePixels':pixels})
                button('Atlas')
                wait_for("!!document.querySelector('[aria-label=\"Anatomical reference\"]')")
            log.flush()
            assert 'texSubImage' not in (OUT/'firefox-driver.log').read_text(), 'Plane texture resize failed'
            (OUT/'firefox-report.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report),flush=True)
        finally:
            if session:
                try:request('DELETE','/session/'+session)
                except Exception:pass
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            display.terminate()
            try:display.wait(timeout=10)
            except subprocess.TimeoutExpired:display.kill();display.wait()


if __name__=='__main__':run()
