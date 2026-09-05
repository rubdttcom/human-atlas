import {useEffect,useState} from 'react';
import {X} from 'lucide-react';
import {Sheet,SheetContent,SheetTitle,SheetDescription} from '@/components/ui/sheet';
import AnatomyScene from './scene';
import type {Atlas,Part,SceneState} from './anatomy';

/** Side-by-side view of the same canonical structure from different sources. Each pane loads the
 *  source atlas in its own frame and isolates one mesh; no cross-source transform is applied. */
const SOURCE_LABEL:Record<string,string>={'denver-vhf':'Denver VHF · female donor VHF','hra-female':'HRA female reference','tcia':'TCIA 003 · female CT','bodyparts3d':'BodyParts3D · male template','composed':'Composite'};
interface Pane {candidate:string;source:string;partId:string}
function Panel({pane}:{pane:Pane}){
 const [atlas,setAtlas]=useState<Atlas|null>(null),[part,setPart]=useState<Part|null>(null),[progress,setProgress]=useState(0),[error,setError]=useState('');
 useEffect(()=>{const abort=new AbortController();setAtlas(null);setPart(null);setProgress(0);setError('');fetch(`/atlases/${pane.source}.json`,{signal:abort.signal}).then(r=>{if(!r.ok)throw new Error('Source atlas unavailable');return r.json();}).then((raw:unknown)=>{const data=raw as Atlas;const found=data.parts.find(p=>p.provenance?.id===pane.candidate||p.id===pane.partId);if(!found)throw new Error('Mesh not found in the source atlas');setPart(found);setAtlas(data);}).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>abort.abort();},[pane.candidate,pane.source,pane.partId]);
 const state:SceneState={explode:0,visible:[],selected:part?[part.id]:[],isolate:true,view:'front',rotate:false,reset:0};
 const record=part?.provenance;
 return <figure className="compare-pane"><div className="compare-scene">{atlas&&part&&<AnatomyScene atlas={atlas} state={state} onSelect={()=>{}} onProgress={setProgress} onError={setError}/>}{!error&&progress<100&&<span className="compare-progress">{progress}%</span>}{error&&<span className="compare-progress" role="alert">{error}</span>}</div><figcaption><strong>{part?.name??pane.partId}</strong><span>{SOURCE_LABEL[pane.source]??pane.source}</span>{record&&<span>{record.geometry_type}{record.granularity&&record.granularity!=='individual'?` · ${record.granularity}`:''} · donor {record.source_donor} · {record.display_space}</span>}{record?.registration&&<span>{record.registration.type}{typeof record.registration.rms_mm==='number'?` · RMS ${record.registration.rms_mm.toFixed(1)} mm`:''}</span>}</figcaption></figure>;
}
export function Compare({candidates,open,onClose}:{candidates:string[];open:boolean;onClose:()=>void}){
 const panes:Pane[]=candidates.slice(0,3).map(candidate=>{const separator=candidate.indexOf(':');return {candidate,source:candidate.slice(0,separator),partId:candidate.slice(separator+1)};});
 return <Sheet open={open} onOpenChange={value=>{if(!value)onClose();}}><SheetContent className="compare-sheet" showCloseButton={false}>
  <header><div><SheetTitle>Compare sources</SheetTitle><SheetDescription>Same catalog structure from different sources, each in its own source frame and scale. Differences reflect donors, modalities and processing; nothing here is registered or validated.</SheetDescription></div><button aria-label="Close comparison" title="Close comparison" onClick={onClose}><X size={20}/></button></header>
  <div className="compare-grid">{open&&panes.map(pane=><Panel key={pane.candidate} pane={pane}/>)}</div>
 </SheetContent></Sheet>;
}
