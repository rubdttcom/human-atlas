import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {LoadedVolume,Plane,SliceFrame,Vec3} from './types.ts';
import {add,directionLabel,dot,pixelPoint,projectPoint,scale,transform} from './coordinates.ts';
import {sampleStage} from './sampler.ts';
import type {ImageSettings,SliceRenderEngine} from './render-engine.ts';

interface Props {
  id:string; title:string; plane:Plane; position:Vec3; volume:LoadedVolume; engine:SliceRenderEngine;
  settings:ImageSettings; resolution:number; frames:Map<string,SliceFrame>; clickAction:'navigate'|'select'; inputStarted:number;
  onPosition:(point:Vec3,inputStarted?:number)=>void; onSelect:(value:number)=>void; onError:(message:string)=>void;
  slider:{value:number;min:number;max:number;step:number;label:string;onChange:(value:number)=>void};
}
export function SlicePanel(props:Props){
  const {id,title,plane,position,volume,engine,settings,resolution,frames,clickAction,onPosition,onSelect,onError,slider,inputStarted}=props;
  const host=useRef<HTMLDivElement>(null),canvas=useRef<HTMLCanvasElement>(null);
  const [size,setSize]=useState([256,256]),[zoom,setZoom]=useState(1),[pan,setPan]=useState<[number,number]>([0,0]);
  const latest=useRef(props);latest.current=props;
  const rendered=useRef<{plane:Plane;width:number;height:number;mpp:number}|null>(null);
  const [pixelStatus,setPixelStatus]=useState('');
  const drag=useRef<{x:number;y:number;pan:[number,number];mode:'pan'|'navigate'}|null>(null);
  const pending=useRef<number>(0),pendingPoint=useRef<Vec3|null>(null);
  const pendingStarted=useRef(0);
  useEffect(()=>{const el=host.current!;const observer=new ResizeObserver(()=>setSize([el.clientWidth,el.clientHeight]));observer.observe(el);return()=>observer.disconnect();},[]);
  useLayoutEffect(()=>{
    const width=Math.max(32,Math.round(Math.min(resolution,size[0]))),height=Math.max(32,Math.round(width*size[1]/Math.max(1,size[0])));
    const mpp=.55/(width*zoom);
    // Crosshair movement within this plane must not drag the image underneath it.
    // Project the fixed region centre onto the shared plane, then apply local pan.
    const center=transform(volume.voxelToStage,volume.manifest.region.initialVoxel);
    const offset=dot(add(plane.origin,scale(center,-1)),plane.normal);
    const displayed={...plane,origin:add(add(center,scale(plane.normal,offset)),add(scale(plane.right,pan[0]),scale(plane.up,pan[1])))};
    // Pointer input is already coalesced per animation frame. Finish all panels
    // in this commit before paint; a second RAF queues stale crosshair frames.
      try{
        engine.render(canvas.current!,displayed,width,height,mpp,settings);
        const ctx=canvas.current!.getContext('2d')!,cross=projectPoint(displayed,position);
        const x=width/2+cross[0]/mpp,y=height/2-cross[1]/mpp;
        ctx.strokeStyle='#65d7cc';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke();
        frames.set(id,{plane:displayed,canvas:canvas.current!,widthMetres:width*mpp,heightMetres:height*mpp,revision:(frames.get(id)?.revision??0)+1,inputStarted});
        rendered.current={plane:displayed,width,height,mpp};
      }catch(error){onError(error instanceof Error?error.message:'Slice rendering failed');}
  },[engine,plane,position,size,zoom,pan,settings,resolution,frames,id,onError,volume,inputStarted]);
  useEffect(()=>()=>{frames.delete(id);cancelAnimationFrame(pending.current);},[frames,id]);
  useEffect(()=>{
    const el=host.current!;
    const wheel=(event:WheelEvent)=>{event.preventDefault();const p=latest.current;const step=event.deltaY>0?-.003:.003;p.onPosition(add(p.position,scale(p.plane.normal,step)));};
    el.addEventListener('wheel',wheel,{passive:false});return()=>el.removeEventListener('wheel',wheel);
  },[]);
  const pointAt=(clientX:number,clientY:number)=>{
    const r=rendered.current,rect=host.current!.getBoundingClientRect();
    return r?pixelPoint(r.plane,(clientX-rect.left)/rect.width*r.width-.5,(clientY-rect.top)/rect.height*r.height-.5,r.width,r.height,r.mpp):null;
  };
  const queue=(point:Vec3)=>{pendingPoint.current=point;pendingStarted.current=performance.now();if(!pending.current)pending.current=requestAnimationFrame(()=>{pending.current=0;if(pendingPoint.current)latest.current.onPosition(pendingPoint.current,pendingStarted.current);});};
  return <section className="slice-panel" aria-label={`${title} slice`} data-slice={id}>
    <header><strong>{title}</strong><span>{pixelStatus||'Drag crosshair · wheel / ↑ ↓'}</span></header>
    <div ref={host} className="slice-image" tabIndex={0} role="application" aria-label={`${title} image navigation`}
      onContextMenu={e=>e.preventDefault()}
      onKeyDown={e=>{if(['ArrowUp','ArrowDown','PageUp','PageDown'].includes(e.key)){e.preventDefault();const sign=['ArrowUp','PageUp'].includes(e.key)?1:-1;onPosition(add(position,scale(plane.normal,sign*(e.key.startsWith('Page')?.015:.003))));}}}
      onPointerDown={e=>{e.currentTarget.focus();const point=pointAt(e.clientX,e.clientY);if(!point)return;e.currentTarget.setPointerCapture(e.pointerId);
        if(e.shiftKey||e.button===1||e.button===2){drag.current={x:e.clientX,y:e.clientY,pan:[...pan],mode:'pan'};return;}
        if(clickAction==='select'){const sample=sampleStage(volume,point);if(sample.state==='acquired'){onSelect(sample.label);setPixelStatus(`HU ${sample.hu.toFixed(0)} · label ${sample.label}`);}else setPixelStatus('Outside supported coverage');return;}
        drag.current={x:e.clientX,y:e.clientY,pan:[...pan],mode:'navigate'};queue(point);
      }}
      onPointerMove={e=>{const d=drag.current;if(!d)return;if(d.mode==='pan'){const r=rendered.current;if(r)setPan([d.pan[0]-(e.clientX-d.x)/Math.max(1,size[0])*r.width*r.mpp,d.pan[1]+(e.clientY-d.y)/Math.max(1,size[1])*r.height*r.mpp]);}else{const point=pointAt(e.clientX,e.clientY);if(point)queue(point);}}}
      onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}>
      <canvas ref={canvas}/>
      <span className="edge top">{directionLabel(plane.up)}</span><span className="edge bottom">{directionLabel(scale(plane.up,-1))}</span>
      <span className="edge left">{directionLabel(scale(plane.right,-1))}</span><span className="edge right">{directionLabel(plane.right)}</span>
    </div>
    <footer>
      <label>{slider.label} <output>{slider.value.toFixed(1)}</output><input aria-label={`${title} position`} type="range" {...{min:slider.min,max:slider.max,step:slider.step,value:slider.value}} onChange={e=>slider.onChange(+e.target.value)}/></label>
      <label>Zoom <input aria-label={`${title} zoom`} type="range" min="0.5" max="4" step="0.05" value={zoom} onChange={e=>setZoom(+e.target.value)}/></label>
      <button onClick={()=>{setZoom(1);setPan([0,0]);}}>Reset view</button>
    </footer>
  </section>;
}
