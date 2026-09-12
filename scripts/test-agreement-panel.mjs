// Presentation test of app/agreement.ts (imported directly; the module uses only erasable TypeScript syntax):
// rows for a real record, for null/zero/missing values and for an undocumented state.
// Usage: node --experimental-strip-types scripts/test-agreement-panel.mjs   (node 22; unflagged from node 23.6)
import {readFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const root = resolve(new URL('..', import.meta.url).pathname);
const mod = await import(pathToFileURL(join(root, 'app/agreement.ts')).href);
const {agreementSections, hasModelAgreement, histogramText, stateText, VOTE_STATES, NO_VOTE_STATES, AGREEMENT_DISCLAIMER} = mod;

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
}
const noGates = agreementSections({vote_rule: 'x'}).map(s => s.title);
if (noGates.includes('Gates before the vote (plan B 2.6)') || noGates.includes('Comparison, not substitution')) fail('gates/comparison sections must be absent without data');
console.log(JSON.stringify({bone_candidates_rendered: atlas.parts.filter(p => p.provenance.instance_family === 'bones').length, instances_rendered: atlas.parts.length, source_equals_composed: true, null_zero_missing_cases: 'ok', wording_rule: 'ok'}));
