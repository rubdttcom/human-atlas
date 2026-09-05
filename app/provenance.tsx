import type {Provenance} from './anatomy';
import {Columns2,Download, ExternalLink} from 'lucide-react';

export function ProvenanceDetails({record,onCompare}:{record:Provenance;onCompare?:()=>void}) {
 function download() {
  const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=`${record.source_asset}-provenance.json`;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 return <section className="provenance" aria-label="Structure provenance">
  <h3>Provenance</h3>
  <dl>{[
   ['Source',record.source],['Source mesh',record.source_asset],['Donor',record.source_donor],
   ['Donor sex',record.source_sex],['Reference sex',record.reference_sex],['Geometry',record.geometry_type+(record.granularity&&record.granularity!=='individual'?` · ${record.granularity}`:'')],
   ['Ontology',record.ontology_term_label?`${record.structure_id} · ${record.ontology_term_label}`:record.structure_id],
   ['Display space',record.display_space],['Canonical space',record.canonical_space??'Not registered'],['VHF registration',record.registration.type],
   ['Confidence',record.confidence===null?'Not assessed':String(record.confidence)],['Review',record.qa_status],
   ['License',record.license],
  ].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
  <p>{record.notes}</p>
  {record.ontology_mapping&&<details><summary>Ontology mapping</summary><p>{record.ontology_mapping}</p></details>}
  <details><summary>File identity</summary><p>{record.source_revision}</p><p>SHA-256: {record.source_chunk_sha256}</p></details>
  {record.geometry_qa&&<details><summary>Source geometry checks</summary><dl>{[
   ['Open boundary edges',record.geometry_qa.boundary_edges],['Nonmanifold edges',record.geometry_qa.nonmanifold_edges],
   ['Degenerate triangles',record.geometry_qa.degenerate_faces],['Self-intersections',record.geometry_qa.self_intersections],
   ['Components',record.geometry_qa.connected_components??'not measured'],['Outlier components',record.geometry_qa.outlier_components??'not measured'],
   ['Anatomical review',record.geometry_qa.anatomical_review],
  ].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></details>}
  <h4>Alternative geometries</h4>
  {record.alternatives.length?<><ul>{record.alternatives.map(id=><li key={id}>{id}</li>)}</ul>{onCompare&&<button className="compare-button" onClick={onCompare}><Columns2 size={15}/>Compare sources side by side</button>}</>:<p>No verified matching alternative imported.</p>}
  <div className="provenance-links"><a href={record.source_url} target="_blank" rel="noreferrer">Dataset <ExternalLink size={14}/></a><a href={record.license_url} target="_blank" rel="noreferrer">License <ExternalLink size={14}/></a><button onClick={download} aria-label="Download structure provenance" title="Download structure provenance"><Download size={16}/></button></div>
 </section>;
}
