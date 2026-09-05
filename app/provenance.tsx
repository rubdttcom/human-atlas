import type {Provenance} from './anatomy';
import {Download, ExternalLink} from 'lucide-react';

export function ProvenanceDetails({record}:{record:Provenance}) {
 function download() {
  const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=`${record.source_asset}-provenance.json`;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 return <section className="provenance" aria-label="Structure provenance">
  <h3>Provenance</h3>
  <dl>{[
   ['Source',record.source],['Source mesh',record.source_asset],['Donor',record.source_donor],
   ['Donor sex',record.source_sex],['Reference sex',record.reference_sex],['Geometry',record.geometry_type],
   ['Display space',record.display_space],['VHF registration',record.registration.type],
   ['Confidence',record.confidence===null?'Not assessed':String(record.confidence)],['Review',record.qa_status],
   ['License',record.license],
  ].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
  <p>{record.notes}</p>
  <details><summary>File identity</summary><p>{record.source_revision}</p><p>SHA-256: {record.source_chunk_sha256}</p></details>
  {record.geometry_qa&&<details><summary>Source geometry checks</summary><dl>{[
   ['Open boundary edges',record.geometry_qa.boundary_edges],['Nonmanifold edges',record.geometry_qa.nonmanifold_edges],
   ['Degenerate triangles',record.geometry_qa.degenerate_faces],['Self-intersections',record.geometry_qa.self_intersections],
   ['Anatomical review',record.geometry_qa.anatomical_review],
  ].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></details>}
  <h4>Alternative geometries</h4>
  {record.alternatives.length?<ul>{record.alternatives.map(id=><li key={id}>{id}</li>)}</ul>:<p>No verified matching alternative imported.</p>}
  <div className="provenance-links"><a href={record.source_url} target="_blank" rel="noreferrer">Dataset <ExternalLink size={14}/></a><a href={record.license_url} target="_blank" rel="noreferrer">License <ExternalLink size={14}/></a><button onClick={download} aria-label="Download structure provenance" title="Download structure provenance"><Download size={16}/></button></div>
 </section>;
}
