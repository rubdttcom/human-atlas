import {useEffect,useMemo,useState} from 'react';
import {Download,X} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Switch} from '@/components/ui/switch';
import type {Atlas,LandmarkPair,RegistrationTransform} from './anatomy';

/** Registration review panel for the composite: shows the recorded landmark fit and lets a reviewer
 *  record a decision per landmark. Decisions stay in this browser (localStorage) until downloaded as
 *  `landmark-review.json`; they are input for `registry/landmark-review.json`, never applied silently. */
type Decision='pending'|'confirmed'|'rejected';
interface Review {reviewer:string;decisions:Record<string,{decision:Decision;comment:string}>}
const KEY='female-atlas-landmark-review';
const empty:Review={reviewer:'',decisions:{}};
function load():Review{try{const raw=localStorage.getItem(KEY);if(raw)return {...empty,...JSON.parse(raw)};}catch{/* storage unavailable */}return empty;}
export function RegistrationPanel({atlas,show,onToggle,onClose}:{atlas:Atlas;show:boolean;onToggle:(v:boolean)=>void;onClose:()=>void}){
 const fit:RegistrationTransform|undefined=useMemo(()=>atlas.registration_report?.transforms.find(t=>t.landmarks&&t.landmarks.length>0),[atlas]);
 const others=useMemo(()=>atlas.registration_report?.transforms.filter(t=>t!==fit)??[],[atlas,fit]);
 const [review,setReview]=useState<Review>(load);
 useEffect(()=>{try{localStorage.setItem(KEY,JSON.stringify(review));}catch{/* storage unavailable */}},[review]);
 const key=(p:LandmarkPair)=>`${p.side}:${p.landmark}`;
 const set=(p:LandmarkPair,patch:Partial<{decision:Decision;comment:string}>)=>setReview(r=>({...r,decisions:{...r.decisions,[key(p)]:{...{decision:'pending' as Decision,comment:''},...r.decisions[key(p)],...patch}}}));
 const download=()=>{const payload={atlas:atlas.version,canonical_space:atlas.canonical_space,transform_id:fit?.id,reviewed_at:new Date().toISOString(),reviewer:review.reviewer,landmarks:(fit?.landmarks??[]).map(p=>({landmark:p.landmark,side:p.side,residual_mm:p.residual_mm,source_point_m:p.source_point_m,target_point_m:p.target_point_m,...(review.decisions[key(p)]??{decision:'pending',comment:''})}))};const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='landmark-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 const counts=(fit?.landmarks??[]).reduce((acc,p)=>{const d=review.decisions[key(p)]?.decision??'pending';acc[d]++;return acc;},{pending:0,confirmed:0,rejected:0} as Record<Decision,number>);
 return <section className="registration-panel glass" aria-label="Registration review">
  <div className="panel-heading"><span>Registration review</span><Button variant="ghost" className="icon-button" onClick={onClose} aria-label="Close registration review"><X size={18}/></Button></div>
  {!fit?<p className="registration-copy">This view has no recorded landmark fit. Open the experimental composite to review its registration.</p>:<>
  <p className="registration-copy">{fit.from} → {fit.to}. {fit.type}: {fit.landmarks?.length} automatic landmarks, RMS {fit.rms_mm?.toFixed(2)} mm, maximum {fit.max_residual_mm?.toFixed(2)} mm, scale {fit.scale?.toFixed(3)}. Status: {fit.review_status}. Landmarks were computed by geometric rules; confirm or reject each one below.</p>
  <label className="registration-toggle"><span>Show landmark pairs in the 3D view</span><Switch checked={show} onCheckedChange={onToggle} aria-label="Show registration landmarks"/></label>
  <p className="registration-legend"><i className="dot target"/>Denver VHF target <i className="dot source"/>TCIA 003 after transform <i className="dot line"/>residual</p>
  <label className="registration-reviewer">Reviewer<input value={review.reviewer} onChange={e=>setReview(r=>({...r,reviewer:e.target.value}))} placeholder="Name or initials" aria-label="Reviewer name"/></label>
  <div className="registration-table"><table><thead><tr><th>Landmark</th><th>Side</th><th>Residual</th><th>Decision</th></tr></thead><tbody>{fit.landmarks?.map(p=>{const d=review.decisions[key(p)];return <tr key={key(p)} className={d?.decision??'pending'}><td>{p.landmark.replace(/_/g,' ')}</td><td>{p.side}</td><td>{p.residual_mm.toFixed(1)} mm</td><td><select aria-label={`Decision for ${p.side} ${p.landmark}`} value={d?.decision??'pending'} onChange={e=>set(p,{decision:e.target.value as Decision})}><option value="pending">Pending</option><option value="confirmed">Confirmed</option><option value="rejected">Rejected</option></select><input aria-label={`Comment for ${p.side} ${p.landmark}`} placeholder="Comment" value={d?.comment??''} onChange={e=>set(p,{comment:e.target.value})}/></td></tr>;})}</tbody></table></div>
  <div className="registration-actions"><span>{counts.confirmed} confirmed · {counts.rejected} rejected · {counts.pending} pending</span><Button variant="ghost" onClick={download}><Download size={15}/>Download review JSON</Button></div>
  {others.length>0&&<details className="registration-others"><summary>Other recorded transforms</summary><ul>{others.map(t=><li key={t.id}><strong>{t.id}</strong> · {t.type}{typeof t.rms_mm==='number'?` · RMS ${t.rms_mm.toFixed(1)} mm`:''} · {t.review_status??'unreviewed'}</li>)}</ul></details>}
  <p className="registration-copy small">Reviewed decisions are not applied automatically. Send the downloaded file to the maintainers; it is merged into <code>registry/landmark-review.json</code> and the fit is recomputed from confirmed landmarks only.</p>
  </>}
 </section>;
}
