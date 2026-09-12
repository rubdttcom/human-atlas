// Presentation of the per-instance model agreement recorded by scripts/ingest-ct-consensus.py
// (source ct-consensus). Pure functions, no imports, so scripts/test-agreement-panel.mjs can run them in node.
// Wording rule: this is agreement between CT segmentation models on the donor's own CT. It is never a
// probability of being right, an anatomical confidence or an independent validation, and the candidate
// name stays pending until an anatomist decides.

export interface ModelVote {state:string;label?:string|null;candidate_ml?:number|null;components_of_label?:number|null;iou_with_consensus?:number|null;extra_candidates?:string[]|null;seed_components?:unknown;processed_fraction?:number|null;absorbed_into?:string|null;fraction_of_union?:number|null}
export interface GatePair {iou_largest_components:number;centroid_offset_mm:number;passed:boolean}
export interface Gates {class_equivalence?:{equivalent_models:string[];passed:boolean};geometric_correspondence?:{pairs:Record<string,GatePair>;passed:boolean};
 laterality?:{applicable:boolean;expected?:string;per_model_side?:Record<string,string>;passed:boolean};
 coverage_eligibility?:{eligible_models_on_union_majority:number;fov_edge_contact_fraction_of_surface:number;fov_edge_contact_ml:number;union_outside_coverage_fraction:number;truncated:boolean}}
export interface DistanceStats {p50:number;p95:number}
export interface ModelAgreement {
 geometry_type?:string;vote_rule?:string;segmentation_models?:string;instance_id?:string;instance_family?:string;role?:string;
 bone_class?:string;review_status?:string;consensus_status?:string;gates?:Gates|null;denver_mesh?:string|null;
 versus_nlm_vhf_ct_label?:{dice:number;volume_ratio_candidate_over_label:number}|null;
 versus_denver_mesh?:{mesh:string;candidate_surface_to_denver_vertices_mm:DistanceStats;denver_vertices_to_candidate_surface_mm:DistanceStats;note:string}|null;
 candidate_name?:string|null;candidate_evidence?:string|null;name_status?:string;hra_name_by_order?:string|null;hra_z_offset_mm?:number|null;
 consensus_ml?:number|null;union_ml?:number|null;agreement_ratio?:number|null;unanimous_fraction?:number|null;
 eligible_models_on_consensus?:Record<string,number>|null;votes_histogram_on_union?:Record<string,number>|null;
 conflict_voxels?:number|null;lost_to_other_winner_ml?:number|null;size_class?:string|null;crosses_skellytour_seam_z?:number[]|null;
 models?:Record<string,ModelVote>|null;source_labels?:Record<string,string>|null;registration_p95_mm?:number|null;
}
export type Row=[string,string];
export interface AgreementSection {title:string;note?:string;rows:Row[]}

export const AGREEMENT_TITLE='Model agreement (CT consensus)';
export const AGREEMENT_DISCLAIMER='Agreement between three open CT bone segmentation models on this donor\'s fresh CT, voted per geometric instance. It is not a probability of being anatomically right, not an anatomical confidence and not an independent validation: the models share training conventions and the same CT. The candidate name is evidence with status pending.';

// Correspondence states of a model's candidate with the instance (scripts/ct-vertebra-instances.py). Only the
// first group are votes for the instance; the second group are reasons a model cast no vote that are not a negative.
export const VOTE_STATES:Record<string,string>={
 voted:'voted; the model labels this bone and its largest component passed the correspondence gates (per-name candidate)',
 matched:'voted; its candidate matches the instance (IoU above the match threshold)',
 split:'voted; its one label spans this and another instance (merged label on its side)',
 merge:'voted; another model\'s label spans this instance and another of this model\'s candidates',
 partial:'voted; partial overlap below the match threshold',
 seed:'voted; the instance was seeded from this model\'s candidate and grown by the others',
 single:'only this model proposed the instance',
};
export const NO_VOTE_STATES:Record<string,string>={
 unsupported:'no vote: the model has no class for this structure (not a negative)',
 unprocessed:'no vote: the region lies outside what the model processed (not a negative)',
 absorbed:'no vote for this instance: the model gave these voxels another label (a naming disagreement, not a negative)',
 negative:'negative: the model processed the region and did not label it as this instance',
 unmatched:'no partner found in the other models',
};

export function hasModelAgreement(record:ModelAgreement|null|undefined):boolean {
 return !!record&&(record.geometry_type==='automatic_segmentation_consensus'||typeof record.vote_rule==='string');
}

const num=(v:number|null|undefined,digits=3,unit='')=>v===null||v===undefined||Number.isNaN(v)?'not recorded':`${Number(v).toFixed(digits).replace(/\.?0+$/,'')}${unit}`;
const pct=(v:number|null|undefined)=>v===null||v===undefined?'not recorded':`${(v*100).toFixed(1)} %`;

export function histogramText(h:Record<string,number>|null|undefined,noun:string):string {
 if(!h||Object.keys(h).length===0) return 'none (no voxels)';
 const keys=Object.keys(h).sort((a,b)=>Number(a)-Number(b));
 const total=keys.reduce((s,k)=>s+h[k],0);
 return keys.map(k=>`${k} ${noun}${k==='1'?'':'s'}: ${h[k].toLocaleString('en-US')} voxels (${total?((h[k]/total)*100).toFixed(1):'0.0'} %)`).join('; ');
}

export function stateText(vote:ModelVote):string {
 const s=vote.state;
 const gloss=VOTE_STATES[s]??NO_VOTE_STATES[s]??'state not in the documented vocabulary';
 const parts=[`${s}: ${gloss}`];
 if(vote.label) parts.push(`label ${vote.label}`);
 if(vote.candidate_ml!==null&&vote.candidate_ml!==undefined) parts.push(`candidate ${num(vote.candidate_ml,2)} mL`);
 if(vote.iou_with_consensus!==null&&vote.iou_with_consensus!==undefined) parts.push(`IoU with consensus ${num(vote.iou_with_consensus)}`);
 if(vote.components_of_label!==null&&vote.components_of_label!==undefined&&vote.components_of_label>1) parts.push(`label in ${vote.components_of_label} components`);
 if(vote.extra_candidates&&vote.extra_candidates.length) parts.push(`extra candidates ${vote.extra_candidates.join(', ')}`);
 if(vote.absorbed_into) parts.push(`absorbed into ${vote.absorbed_into} (${pct(vote.fraction_of_union)} of the union)`);
 if(vote.processed_fraction!==null&&vote.processed_fraction!==undefined) parts.push(`processed fraction ${pct(vote.processed_fraction)}`);
 return parts.join(' · ');
}

export function agreementSections(record:ModelAgreement):AgreementSection[] {
 const models=record.models??{};
 const modelNames=Object.keys(models);
 const votes=modelNames.filter(m=>models[m].state in VOTE_STATES);
 const noVotes=modelNames.filter(m=>!(models[m].state in VOTE_STATES));
 const identity:AgreementSection={title:'Identity',rows:[
  ['Instance',`${record.instance_id??'not recorded'} (${record.instance_family??'family not recorded'}, role ${record.role??'not recorded'}); id is geometric, cranial to caudal`],
  ['Candidate name',record.candidate_name?`${record.candidate_name} · status ${record.name_status??'not recorded'} (evidence, not a decision)`:`none · status ${record.name_status??'not recorded'}`],
  ['Candidate evidence',record.candidate_evidence??'not recorded'],
  ['Same-donor HRA chain',record.hra_name_by_order?`${record.hra_name_by_order} by order from the sacrum, z offset ${num(record.hra_z_offset_mm,1,' mm')}`:'not applicable'],
  ['Source labels',record.source_labels&&Object.keys(record.source_labels).length?Object.entries(record.source_labels).map(([m,l])=>`${m}: ${l}`).join('; '):'none recorded'],
 ]};
 const consensus=record.consensus_ml, union=record.union_ml;
 const vote:AgreementSection={title:'Vote',note:record.vote_rule??'vote rule not recorded',rows:[
  ['Models voting',`${votes.length} of ${modelNames.length}${modelNames.length?` (${votes.join(', ')||'none'})`:''}`],
  ['Consensus volume',consensus===null||consensus===undefined?'not recorded':`${num(consensus,2)} mL: voxels where a strict majority of the eligible models vote this instance`],
  ['Union volume',union===null||union===undefined?'not recorded':`${num(union,2)} mL: voxels where any model votes this instance`],
  ['Agreement ratio',record.agreement_ratio===null||record.agreement_ratio===undefined?(union===0?'undefined: no union voxels':'not recorded'):`${num(record.agreement_ratio)} = consensus / union volume (denominator: union voxels)`],
  ['Unanimous fraction',record.unanimous_fraction===null||record.unanimous_fraction===undefined?(consensus===0?'undefined: no consensus voxels':'not recorded'):`${pct(record.unanimous_fraction)} of the consensus voxels carry a vote from every eligible model (denominator: consensus voxels)`],
  ['Eligible models on consensus voxels',histogramText(record.eligible_models_on_consensus,'eligible model')+' (a model is eligible where it processed the region and has a class for the structure)'],
  ['Votes on union voxels',histogramText(record.votes_histogram_on_union,'model')+' (how many models vote this instance at each union voxel)'],
  ['Conflict voxels',record.conflict_voxels===null||record.conflict_voxels===undefined?'not recorded':`${record.conflict_voxels.toLocaleString('en-US')} union voxels where another model votes a different instance${record.conflict_voxels===0?' (none)':''}`],
  ['Lost to another winner',record.lost_to_other_winner_ml===null||record.lost_to_other_winner_ml===undefined?'not recorded':`${num(record.lost_to_other_winner_ml,2)} mL of the union assigned to another instance in the winner map`],
  ['Size class',record.size_class??'not recorded'],
  ['Skellytour chunk seams crossed',record.crosses_skellytour_seam_z&&record.crosses_skellytour_seam_z.length?`z = ${record.crosses_skellytour_seam_z.join(', ')} (seam check: no identity change found)`:'none'],
 ]};
 const perModel:AgreementSection={title:'Per model',note:record.segmentation_models??'segmentation models not recorded',rows:modelNames.length?modelNames.map(m=>[m,stateText(models[m])] as Row):[['Models','none recorded']]};
 if(noVotes.length) perModel.rows.push(['Not voting',`${noVotes.map(m=>`${m} (${models[m].state})`).join(', ')}: see the state gloss; only "negative" is a vote against`]);
 const placement:AgreementSection={title:'Placement',rows:[
  ['Registration',record.registration_p95_mm===null||record.registration_p95_mm===undefined?'not recorded':`rigid same-donor pelvis fit, p95 ${num(record.registration_p95_mm,2,' mm')}; agreement is computed on the CT grid and does not change with registration`],
 ]};
 const sections=[identity,vote,perModel,placement];
 if(record.gates){
  const g=record.gates;
  const rows:Row[]=[];
  if(g.class_equivalence) rows.push(['Class equivalence',`${g.class_equivalence.passed?'passed':'failed'}: ${g.class_equivalence.equivalent_models.join(', ')} (registry/ct-label-equivalence.json; group labels never meet individual bones)`]);
  if(g.geometric_correspondence){const pairs=Object.entries(g.geometric_correspondence.pairs);rows.push(['Geometric correspondence',`${g.geometric_correspondence.passed?'passed':'failed'}: `+(pairs.length?pairs.map(([k,v])=>`${k} IoU ${num(v.iou_largest_components)} · centroid ${num(v.centroid_offset_mm,1,' mm')}${v.passed?'':' (failed)'}`).join('; '):'single model, no pair')+' (largest components; IoU >= 0.50 and <= 15 mm per pair)']);}
  if(g.laterality) rows.push(['Laterality',g.laterality.applicable?`${g.laterality.passed?'passed':'failed'}: expected ${g.laterality.expected}; ${Object.entries(g.laterality.per_model_side??{}).map(([m,s])=>`${m} ${s}`).join(', ')} (RAS +x = subject right, organ anchor)`:'not applicable (midline bone)']);
  if(g.coverage_eligibility){const c=g.coverage_eligibility;rows.push(['Coverage',`${c.eligible_models_on_union_majority} eligible models on the union; ${pct(c.fov_edge_contact_fraction_of_surface)} of the surface on the CT field-of-view edge (${num(c.fov_edge_contact_ml,2,' mL')})${c.truncated?' · truncated: the acquisition cuts this bone':''}`]);}
  sections.push({title:'Gates before the vote (plan B 2.6)',note:record.consensus_status?`status ${record.consensus_status} · ${record.review_status??'review status not recorded'}`:undefined,rows});
 }
 if(record.versus_nlm_vhf_ct_label||record.versus_denver_mesh){
  const rows:Row[]=[];
  const t=record.versus_nlm_vhf_ct_label;
  rows.push(['Current CT label (nlm-vhf-ct)',t?`Dice ${num(t.dice)} · volume ratio candidate/label ${num(t.volume_ratio_candidate_over_label)}`:'no TotalSegmentator label for this bone']);
  const d=record.versus_denver_mesh;
  rows.push(['Denver mesh (cryosections)',d?`${d.mesh}: candidate surface to Denver vertices p50 ${num(d.candidate_surface_to_denver_vertices_mm.p50,1,' mm')} · p95 ${num(d.candidate_surface_to_denver_vertices_mm.p95,1,' mm')}; Denver vertices to candidate surface p50 ${num(d.denver_vertices_to_candidate_surface_mm.p50,1,' mm')} · p95 ${num(d.denver_vertices_to_candidate_surface_mm.p95,1,' mm')}. Registration and posture differences are included in these distances; they do not separate segmentation error from placement.`:record.denver_mesh?`${record.denver_mesh} not compared`:'no Denver mesh for this bone']);
  sections.push({title:'Comparison, not substitution',note:'Denver measured geometry stays the atlas reference where it exists; any replacement is a recorded per-bone decision (plan B 2.6).',rows});
 }
 return sections;
}
