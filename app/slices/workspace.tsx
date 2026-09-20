import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import AnatomyScene from '../scene';
import {DEFAULT_VISIBLE,type Atlas,type SceneState} from '../anatomy';
import {add,dot,obliquePlane,orthogonalPlane,scale,transform} from './coordinates.ts';
import {VolumeLoader,sha256} from './volume-loader.ts';
import {SliceRenderEngine,type ImageSettings} from './render-engine.ts';
import {SlicePanel} from './slice-panel';
import type {LoadedVolume,SliceFrame,Vec3,View} from './types.ts';
import './slices.css';

export default function SlicesWorkspace({onExit,previousSource}:{onExit:()=>void;previousSource:string}){
  const [loaded,setLoaded]=useState<{volume:LoadedVolume;engine:SliceRenderEngine;atlas:Atlas}|null>(null);
  const [error,setError]=useState(''),[retry,setRetry]=useState(0),[position,setPosition]=useState<Vec3>([0,0,0]);
  const [inputStarted,setInputStarted]=useState(0);
  const [oblique,setOblique]=useState(false),[angles,setAngles]=useState<[number,number]>([0,0]);
  const [selected,setSelected]=useState(5),[notice,setNotice]=useState(''),[showPlanes,setShowPlanes]=useState(true);
  const [windowWidth,setWindowWidth]=useState(400),[level,setLevel]=useState(50),[opacity,setOpacity]=useState(.8),[fill,setFill]=useState(false);
  const [resolution,setResolution]=useState(384),[clickAction,setClickAction]=useState<'navigate'|'select'>('navigate');
  const [activePanel,setActivePanel]=useState<View>('axial'),[progress,setProgress]=useState(0);
  const frames=useRef(new Map<string,SliceFrame>()).current;
  const fail=useCallback((message:string)=>setError(message),[]);
  useEffect(()=>{
    const loader=new VolumeLoader(),abort=new AbortController();let active=true,engine:SliceRenderEngine|undefined;
    setLoaded(null);setError('');frames.clear();
    (async()=>{
      const volume=await loader.load(new URL('/volumes/nlm-abdomen/manifest.json',location.href).href);
      const response=await fetch('/atlases/nlm-vhf-ct.json',{signal:abort.signal});
      if(!response.ok)throw new Error('CT mesh catalogue unavailable');
      const bytes=await response.arrayBuffer();
      if(await sha256(bytes)!==volume.manifest.inputs.atlas.sha256)throw new Error('CT mesh catalogue changed; rebuild the preview');
      const source=JSON.parse(new TextDecoder().decode(bytes)) as Atlas;
      const ids=new Set(volume.manifest.labels.map(l=>l.assetId));
      const parts=source.parts.filter(p=>ids.has(p.id)),chunkIds=[...new Set(parts.map(p=>p.chunk))];
      const atlas={...source,parts:parts.map(p=>({...p,chunk:chunkIds.indexOf(p.chunk)})),chunks:chunkIds.map(i=>source.chunks[i])};
      if(!active)return;
      engine=new SliceRenderEngine(volume,fail);
      setPosition(transform(volume.voxelToStage,volume.manifest.region.initialVoxel));
      setLoaded({volume,engine,atlas});
    })().catch(e=>{if(active)setError(e instanceof Error?e.message:'Volume unavailable');});
    return()=>{active=false;abort.abort();loader.cancel();engine?.dispose();frames.clear();};
  },[retry,fail,frames]);
  const select=useCallback((value:number)=>{
    if(loaded?.volume.manifest.labels.some(l=>l.value===value)){setSelected(value);setNotice('');}
    else setNotice(value===0?'No structure label at this pixel.':'Overlay unavailable: this label has no mapped structure in the abdominal view.');
  },[loaded]);
  const move=useCallback((point:Vec3,startedAt=performance.now())=>{
    if(!loaded)return;const voxel=transform(loaded.volume.stageToVoxel,point);
    if(voxel.every((v,i)=>v>=-1e-6&&v<=loaded.volume.dimensions[i]-1+1e-6)){setInputStarted(startedAt);setPosition(point);setNotice('');}
    else setNotice('Position is outside the abdominal preview.');
  },[loaded]);
  const selection=loaded?.volume.manifest.labels.find(l=>l.value===selected);
  const settings=useMemo<ImageSettings>(()=>({width:windowWidth,level,selected,opacity,fill,color:selection?.color??'#ffffff'}),[windowWidth,level,selected,opacity,fill,selection]);
  const sceneState=useMemo<SceneState>(()=>({explode:0,visible:DEFAULT_VISIBLE,selected:selection?[selection.assetId]:[],isolate:false,view:'three-quarter',rotate:false,reset:0}),[selection]);
  const planes=useMemo(()=>{
    if(!loaded)return null;
    return {axial:orthogonalPlane(loaded.volume.voxelToStage,position,'axial'),coronal:orthogonalPlane(loaded.volume.voxelToStage,position,'coronal'),sagittal:orthogonalPlane(loaded.volume.voxelToStage,position,'sagittal')};
  },[loaded,position]);
  const tilted=useMemo(()=>planes?obliquePlane(planes.axial,...angles):null,[planes,angles]);
  const colors=useMemo(()=>Object.fromEntries(loaded?.volume.manifest.labels.map(l=>[l.assetId,l.color])??[]),[loaded]);
  const axisPosition=(axis:number,value:number)=>{if(!loaded)return;const p=transform(loaded.volume.stageToVoxel,position);p[axis]=value;move(transform(loaded.volume.voxelToStage,p));};
  const centre=()=>{
    if(!selection||!loaded)return;
    const physical=selection.bounds[0].map((v,i)=>(v+selection.bounds[1][i])/2) as Vec3;
    const voxel=transform(loaded.volume.stageToVoxel,physical).map((v,i)=>Math.max(0,Math.min(loaded.volume.dimensions[i]-1,v))) as Vec3;
    setPosition(transform(loaded.volume.voxelToStage,voxel));
  };
  const voxel=loaded?transform(loaded.volume.stageToVoxel,position):[0,0,0];
  const sourceCenter=loaded?transform(loaded.volume.voxelToStage,loaded.volume.manifest.region.initialVoxel):[0,0,0] as Vec3;
  const distance=tilted?dot(add(position,scale(sourceCenter,-1)),tilted.normal)*1000:0;
  return <main className="slices-workspace">
    <header className="slices-heading"><div><span className="slices-kicker">FEMALE VHF · ORIGINAL CT</span><h1>Slices <small>Abdomen · 7 mapped parts</small></h1></div><nav aria-label="Viewer mode"><button onClick={onExit}>Atlas</button><button aria-current="page">Slices</button></nav></header>
    <p className="source-transition">CT acquisition with its CT-derived structures. This view shows only the seven structures with an exact CT label-to-mesh mapping; your {previousSource} atlas state is preserved for return. Preview spacing: 2.8125 × 2.8125 × 3 mm.</p>
    {!loaded||error?<section className="slices-message" role={error?'alert':'status'}><h2>{error?'Slices unavailable':'Loading abdominal preview…'}</h2><p>{error||'Checking source identity, image grid and file integrity.'}</p>{error&&<><p>If retrying does not help, the local preview may need to be prepared again. The setup instructions are in the project’s reproducibility guide.</p><button onClick={()=>setRetry(n=>n+1)}>Retry preview</button></>}</section>:<>
      <div className="slices-body">
        <aside className="slices-controls" aria-label="Slice controls">
          <div className="segmented"><button aria-pressed={!oblique} onClick={()=>setOblique(false)}>Orthogonal</button><button aria-pressed={oblique} onClick={()=>{setAngles([0,0]);setOblique(true);}}>Oblique</button></div>
          <label>Structure<select aria-label="Slice structure" value={selected} onChange={e=>select(+e.target.value)}>{loaded.volume.manifest.labels.map(l=><option key={l.value} value={l.value}>{l.name}</option>)}</select></label>
          <button onClick={centre}>Center on structure</button>
          <label>Click action<select aria-label="Click action" value={clickAction} onChange={e=>setClickAction(e.target.value as 'navigate'|'select')}><option value="navigate">Move crosshair</option><option value="select">Select label</option></select></label>
          <div className="segmented"><button onClick={()=>{setWindowWidth(400);setLevel(50);}}>Soft tissue</button><button onClick={()=>{setWindowWidth(1800);setLevel(400);}}>Bone</button></div>
          <label>Window width <input aria-label="Window width" type="number" min="1" max="10000" value={windowWidth} onChange={e=>setWindowWidth(Math.max(1,Math.min(10000,+e.target.value||1)))}/></label>
          <label>Window level <input aria-label="Window level" type="number" min="-2000" max="4000" value={level} onChange={e=>setLevel(Math.max(-2000,Math.min(4000,+e.target.value||0)))}/></label>
          <label>Overlay opacity <input aria-label="Overlay opacity" type="range" min="0" max="1" step="0.05" value={opacity} onChange={e=>setOpacity(+e.target.value)}/></label>
          <label className="check"><input aria-label="Fill mask" type="checkbox" checked={fill} onChange={e=>setFill(e.target.checked)}/>Fill mask (boundary is default)</label>
          <label className="check"><input aria-label="Show planes in 3D" type="checkbox" checked={showPlanes} onChange={e=>setShowPlanes(e.target.checked)}/>Show planes in 3D</label>
          {oblique&&<fieldset><legend>Oblique orientation</legend>{(['Initial right','Initial up'] as const).map((name,i)=><label key={name}>{name} · {angles[i]}°<input aria-label={`${name} angle`} type="range" min="-90" max="90" step="1" value={angles[i]} onChange={e=>setAngles(a=>a.map((v,j)=>j===i?+e.target.value:v) as [number,number])}/></label>)}<button onClick={()=>setAngles([0,0])}>Reset orientation</button></fieldset>}
          <label>Display resolution<select aria-label="Display resolution" value={resolution} onChange={e=>setResolution(+e.target.value)}><option value="384">Standard · 384 px</option><option value="192">Reduced · 192 px</option></select></label>
          <label className="mobile-slice-choice">Active slice<select aria-label="Active slice" value={activePanel} onChange={e=>setActivePanel(e.target.value as View)}><option>axial</option><option>coronal</option><option>sagittal</option></select></label>
          <p className="slice-help">Shift-drag to pan. Zoom is independent per panel. Orbiting the body leaves the slices fixed.</p>
          <details><summary>Source &amp; limits</summary><p>{loaded.volume.manifest.derivedNotice}</p><p>{loaded.volume.manifest.overlayNotice}</p><p>Slice-compatible structures: {loaded.volume.manifest.labels.map(l=>l.name).join(', ')}.</p><p>Name status: {String(selection?.provenance.name_status??'not recorded; source model label')}. Machine status: {String(selection?.provenance.review_status??'not recorded')}. QA status: {String(selection?.provenance.qa_status??'not recorded')}. No anatomical review.</p><p>CT preview: 2.8125 × 2.8125 × 3 mm; not native resolution. Checkered pixels are outside supported coverage.</p><p>{loaded.volume.manifest.coverage.sourceLimit}</p><p>Exploded geometry is disabled in Slices.</p><p>{selection?.name}: {(selection?.provenance.registration as {review_status?:string})?.review_status??'placement unreviewed'}</p></details>
        </aside>
        <div className={`slice-grid ${oblique?'oblique':''}`} data-active={activePanel}>
          <section className="slice-three"><header><strong>3D · CT structures</strong><span>{progress<100?`Loading meshes ${progress}%`:'Drag to orbit'}</span></header><div className="slice-three-host"><AnatomyScene atlas={loaded.atlas} state={sceneState} onSelect={id=>{const l=loaded.volume.manifest.labels.find(l=>l.assetId===id);if(l)select(l.value);}} onProgress={setProgress} onError={fail} slices={{frames,visible:showPlanes,center:sourceCenter,colors,inputStarted}}/></div></section>
          {planes&&(!oblique?(['axial','coronal','sagittal'] as const).map(view=>{
            const axis=view==='axial'?2:view==='coronal'?1:0;
            return <SlicePanel key={view} id={view} title={view[0].toUpperCase()+view.slice(1)} plane={planes[view]} position={position} volume={loaded.volume} engine={loaded.engine} inputStarted={inputStarted} settings={settings} resolution={resolution} frames={frames} clickAction={clickAction} onPosition={move} onSelect={select} onError={fail} slider={{value:voxel[axis],min:0,max:loaded.volume.dimensions[axis]-1,step:1,label:`CT ${['X','Y','Z'][axis]} ${transform(loaded.volume.manifest.levels[0].voxelToSourcePhysical,voxel as Vec3)[axis].toFixed(1)} mm · slice`,onChange:value=>axisPosition(axis,value)}}/>;
          }):tilted&&<SlicePanel key="oblique" id="oblique" title="Oblique" plane={tilted} position={position} volume={loaded.volume} engine={loaded.engine} inputStarted={inputStarted} settings={settings} resolution={resolution} frames={frames} clickAction={clickAction} onPosition={move} onSelect={select} onError={fail} slider={{value:distance,min:-300,max:300,step:1,label:'Normal position (mm)',onChange:value=>move(add(position,scale(tilted.normal,(value-distance)/1000)))}}/>)}
        </div>
      </div>
      <footer className="slices-footer"><span role="status">{notice||`${selection?.name} · stage ${position.map(v=>(v*1000).toFixed(1)).join(', ')} mm`}</span><span>{loaded.volume.manifest.attribution}</span></footer>
    </>}
  </main>;
}
