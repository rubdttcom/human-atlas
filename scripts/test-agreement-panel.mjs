// Presentation test of app/agreement.ts (imported directly; the module uses only erasable TypeScript syntax):
// rows for a real record, for null/zero/missing values and for an undocumented state.
// Usage: node --experimental-strip-types scripts/test-agreement-panel.mjs   (node 22; unflagged from node 23.6)
import {readFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const root = resolve(new URL('..', import.meta.url).pathname);
const mod = await import(pathToFileURL(join(root, 'app/agreement.ts')).href);
const {agreementSections, hasModelAgreement, histogramText, stateText, VOTE_STATES, NO_VOTE_STATES, AGREEMENT_DISCLAIMER, hasPosture, postureSection, POSTURE_DISCLAIMER} = mod;

const fail = (m) => { console.error('FAIL: ' + m); process.exit(1); };
const rows = (record) => Object.fromEntries(agreementSections(record).flatMap(s => s.rows));
const text = (record) => JSON.stringify(agreementSections(record));

// Wording rule: never present agreement as correctness, confidence or validation.
for (const banned of ['probability of correctness', 'anatomical confidence', 'validated', 'independent validation of']) {
  if (AGREEMENT_DISCLAIMER.toLowerCase().includes(banned) && !AGREEMENT_DISCLAIMER.toLowerCase().includes('not ' + banned) && !AGREEMENT_DISCLAIMER.toLowerCase().includes('not an ' + banned)) fail('disclaimer uses ' + banned + ' affirmatively');
}
if (!/not a probability/.test(AGREEMENT_DISCLAIMER) || !/not an independent validation/.test(AGREEMENT_DISCLAIMER)) fail('disclaimer must deny probability and independent validation');

// 1. A real record from the shipped source atlas and its copy in the composite must render identically.
const atlas = JSON.parse(readFileSync(join(root, 'public/atlases/ct-consensus.json'), 'utf8'));
const composed = JSON.parse(readFileSync(join(root, 'public/atlases/composed.json'), 'utf8'));
const v20 = atlas.parts.find(p => p.id === 'CTCONS:VHF:V20').provenance;
const v20c = composed.parts.find(p => p.id === 'ct-consensus:CTCONS:VHF:V20').provenance;
if (!hasModelAgreement(v20) || !hasModelAgreement(v20c)) fail('consensus records must be detected');
if (text(v20) !== text(v20c)) fail('source and composed copies render differently');
const r = rows(v20);
if (!r['Agreement ratio'].startsWith('0.819') || !r['Agreement ratio'].includes('denominator: union voxels')) fail('agreement ratio row: ' + r['Agreement ratio']);
if (!r['Unanimous fraction'].includes('81.6 %') || !r['Unanimous fraction'].includes('denominator: consensus voxels')) fail('unanimous row: ' + r['Unanimous fraction']);
if (!r['Candidate name'].includes('status pending') || !r['Candidate name'].includes('not a decision')) fail('candidate name must stay pending: ' + r['Candidate name']);
if (!r['Models voting'].startsWith('3 of 3')) fail('votes: ' + r['Models voting']);
if (!r['Votes on union voxels'].includes('3 models: 45,166 voxels')) fail('histogram: ' + r['Votes on union voxels']);
for (const m of ['totalseg', 'moose', 'skellytour']) if (!r[m] || !r[m].startsWith('matched: voted')) fail('per-model row ' + m + ': ' + r[m]);
// Every shipped instance renders, and every recorded state is in the documented vocabulary.
for (const part of atlas.parts) {
  const rr = rows(part.provenance);
  for (const [m, v] of Object.entries(part.provenance.models)) {
    if (!(v.state in VOTE_STATES) && !(v.state in NO_VOTE_STATES)) fail(`${part.id}: undocumented state ${v.state}`);
    if (!rr[m]) fail(`${part.id}: no row for model ${m}`);
  }
}
const unsupported = atlas.parts.find(p => Object.values(p.provenance.models).some(v => v.state === 'unsupported'));
if (unsupported) {
  const rr = rows(unsupported.provenance);
  if (!rr['Not voting'] || !rr['Not voting'].includes('only "negative" is a vote against')) fail('unsupported state must be separated from a negative vote');
  if (!rr['Models voting'].startsWith('2 of 3')) fail('unsupported model must not count as voting: ' + rr['Models voting']);
}

// 2. Nulls, zeros, empty histograms and missing fields render explicit text, never NaN/undefined.
const empty = {geometry_type: 'automatic_segmentation_consensus', consensus_ml: 0, union_ml: 0, agreement_ratio: null, unanimous_fraction: null,
  eligible_models_on_consensus: {}, votes_histogram_on_union: {}, conflict_voxels: 0, models: {}, name_status: 'pending', candidate_name: null};
const e = rows(empty);
if (e['Agreement ratio'] !== 'undefined: no union voxels') fail('null ratio with zero union: ' + e['Agreement ratio']);
if (e['Unanimous fraction'] !== 'undefined: no consensus voxels') fail('null unanimous with zero consensus: ' + e['Unanimous fraction']);
if (!e['Eligible models on consensus voxels'].startsWith('none (no voxels)')) fail('empty histogram: ' + e['Eligible models on consensus voxels']);
if (!e['Conflict voxels'].includes('0 union voxels') || !e['Conflict voxels'].includes('(none)')) fail('zero conflicts: ' + e['Conflict voxels']);
if (e['Candidate name'] !== 'none · status pending') fail('missing candidate: ' + e['Candidate name']);
if (e['Models voting'] !== '0 of 0') fail('no models: ' + e['Models voting']);
const t = text(empty);
if (/NaN|undefined(?!:)|null/.test(t.replace(/undefined: no/g, ''))) fail('raw NaN/undefined/null leaked into the panel: ' + t);
const bare = rows({vote_rule: 'x'});
if (Object.values(bare).some(v => /NaN|undefined|null/.test(v) && !v.startsWith('undefined:'))) fail('missing fields leak raw values: ' + JSON.stringify(bare));
if (bare['Agreement ratio'] !== 'not recorded' || bare['Instance'] !== 'not recorded (family not recorded, role not recorded); id is geometric, cranial to caudal') fail('missing fields: ' + bare['Agreement ratio'] + ' / ' + bare['Instance']);
if (!hasModelAgreement({vote_rule: 'x'}) || hasModelAgreement({}) || hasModelAgreement(null)) fail('detection');
if (histogramText({'2': 1, '1': 3}, 'model') !== '1 model: 3 voxels (75.0 %); 2 models: 1 voxels (25.0 %)') fail('histogram order/percent: ' + histogramText({'2': 1, '1': 3}, 'model'));
if (!stateText({state: 'wizardry'}).includes('state not in the documented vocabulary')) fail('unknown state gloss');
if (!stateText({state: 'absorbed', absorbed_into: 'sacrum', fraction_of_union: 0.9}).includes('absorbed into sacrum (90.0 % of the union)')) fail('absorbed text');
// 3. Per-name bone candidates: gates and comparison sections render; comparison never claims substitution.
const bone = atlas.parts.find(p => p.provenance.instance_family === 'bones');
if (bone) {
  const secs = agreementSections(bone.provenance);
  const titles = secs.map(s => s.title);
  if (!titles.includes('Gates before the vote (plan B 2.6)') || !titles.includes('Comparison, not substitution')) fail('bone candidate must show gates and comparison: ' + titles);
  const br = rows(bone.provenance);
  if (!br['Geometric correspondence'].startsWith('passed') || !br['Class equivalence'].startsWith('passed')) fail('gates text: ' + br['Geometric correspondence']);
  if (!/Registration and posture differences are included/.test(br['Denver mesh (cryosections)'])) fail('Denver comparison must state that placement error is included');
  if (!br['Candidate name'].includes('status pending')) fail('bone candidate name must stay pending');
  for (const m of Object.keys(bone.provenance.models)) if (!br[m] || !br[m].startsWith('voted: voted')) fail('bone per-model row ' + m + ': ' + br[m]);
  // 4. Shape check section: present for every bone candidate; wording never reads as validation; missing record says "not run".
  if (!titles.includes('Shape check (plan B 2.6)')) fail('bone candidate must show the shape check section: ' + titles);
  for (const p of atlas.parts.filter(p => p.provenance.instance_family === 'bones')) {
    const r = rows(p.provenance);
    const sc = p.provenance.shape_check;
    if (!sc) { if (r['Shape check'] !== 'not run: candidate pending the shape check of plan B 2.6, not an accepted atlas candidate') fail('missing shape check wording: ' + r['Shape check']); continue; }
    const t = r['Shape (own rigid fit to the HU = 300 edge)'];
    if (!t || /validated|confirmed|correct\b/.test(t)) fail('shape check wording: ' + t);
    if (sc.decision === 'reaches-denver-baseline' && !t.includes('reaches the Denver baseline')) fail('reaches text: ' + t);
    if (sc.decision === 'above-denver-baseline' && !t.includes('not met')) fail('above text: ' + t);
    if (sc.decision === 'no-class-baseline' && !t.includes('no acceptance')) fail('no-baseline text: ' + t);
    if (/NaN|undefined|null/.test(t)) fail('shape check leaks raw values: ' + t);
  }
  const notRun = rows({...bone.provenance, shape_check: null});
  if (!notRun['Shape check'] || !notRun['Shape check'].startsWith('not run')) fail('shape_check null must render as not run: ' + notRun['Shape check']);
  const oddDecision = rows({...bone.provenance, shape_check: {decision: 'wizardry', passed: null}});
  if (!oddDecision['Shape (own rigid fit to the HU = 300 edge)'].includes('not in the documented vocabulary')) fail('unknown shape decision gloss');
}
const noGates = agreementSections({vote_rule: 'x'}).map(s => s.title);
if (noGates.includes('Gates before the vote (plan B 2.6)') || noGates.includes('Comparison, not substitution')) fail('gates/comparison sections must be absent without data');
console.log(JSON.stringify({bone_candidates_rendered: atlas.parts.filter(p => p.provenance.instance_family === 'bones').length, instances_rendered: atlas.parts.length, source_equals_composed: true, null_zero_missing_cases: 'ok', wording_rule: 'ok'}));

// 4. Trunk posture panel (plan B stage 0): renders for consensus instances and for CT labels, never as validation.
const ps = postureSection(v20);
if (!ps || !hasPosture(v20)) fail('V20 must carry a posture panel');
const pr = Object.fromEntries(ps.rows);
if (!/norm [0-9.]+ mm/.test(pr['Relative to the pelvis']) || !/not separated/.test(pr['Relative to the pelvis'])) fail('relative offset row must say the mixture is not separated: ' + pr['Relative to the pelvis']);
if (!/not identified by this calculation/.test(pr['Pelvis-anchor offset'])) fail('anchor offset must not be attributed to a cause: ' + pr['Pelvis-anchor offset']);
if (!/beyond|within/.test(pr['Heuristic discrepancy threshold']) || !/not an error bound/.test(pr['Heuristic discrepancy threshold'])) fail('threshold row must be heuristic, beyond/within: ' + pr['Heuristic discrepancy threshold']);
if (/registration not posture|posture \+ segmentation\)/.test(JSON.stringify(ps))) fail('posture panel must not attribute the offset to a single cause');
if (!/SHA-256 [0-9a-f]{64}/.test(pr['Report'])) fail('posture panel must show the report hash');
if (JSON.stringify(ps) !== JSON.stringify(postureSection(v20c))) fail('posture panel differs between source and composite copies');
for (const s of [JSON.stringify(ps), POSTURE_DISCLAIMER]) if (/validated|confirmed|correct\b/i.test(s) && !/nothing is corrected/.test(s)) fail('posture wording must never read as validation: ' + s);
if (!/nothing is corrected/i.test(ps.note) || !/nothing is anatomy/i.test(ps.note)) fail('posture note must say nothing is corrected and nothing is anatomy');
const nlm = JSON.parse(readFileSync(join(root, 'public/atlases/nlm-vhf-ct.json'), 'utf8'));
const liver = nlm.parts.find(p => p.provenance.label_name === 'liver').provenance;
const ls = postureSection(liver);
if (!ls || !/nearest measured vertebral level/.test(Object.fromEntries(ls.rows)['Level used'])) fail('CT label context must state the nearest-level link');
const l1 = nlm.parts.find(p => p.provenance.label_name === 'vertebrae_L1').provenance;
const l1rows = Object.fromEntries(postureSection(l1).rows);
if (!/voted into/.test(l1rows['Level used'])) fail('vertebra label must link to the instance it voted into');
if (l1.trunk_posture_context.linked_instance_ids.length > 1) {
  if (!/split label/.test(l1rows['Level used']) || !/linked instances V20, V21/.test(l1rows['Level used'])) fail('split label must show every linked instance: ' + l1rows['Level used']);
  for (const id of l1.trunk_posture_context.linked_instance_ids) if (!l1rows['Linked ' + id]) fail('split label must render a row per linked instance: ' + id);
}
const nm = postureSection({posture_offset: {status: 'not-measured', report: 'r', report_sha256: 'x'}});
if (!nm || nm.rows[0][1] !== 'not-measured') fail('not-measured posture must render explicitly');
if (hasPosture({}) || hasPosture(null) || postureSection({}) !== null) fail('records without a measurement must not show a posture panel');
if (/NaN|undefined|null/.test(JSON.stringify(ps))) fail('raw NaN/undefined/null in the posture panel');
