"""Check that the per-instance model agreement of source `ct-consensus` is propagated unchanged and stays honest.

Checks (no metric is recomputed from voxels; the instance tables written by ct-vertebra-instances.py are the reference):
1. Every meshed instance carries the agreement fields in the source atlas, in manifests/ct-consensus.json and in the
   composite, and the three copies are equal (no drift between source and transformed geometry metadata).
2. Every value equals the instance table (generated/ct-vertebra-instances-nlm.json, generated/ct-rib-instances-nlm-*.json).
3. Internal consistency of the recorded figures: ratios in [0, 1]; agreement_ratio = consensus_ml / union_ml (3 dp);
   histogram totals equal the consensus and union voxel counts implied by the volumes and the CT voxel size;
   every model state is in the documented vocabulary; voting states carry a label, non-voting states do not;
   source_labels equals the labels of the voting models; unsupported/unprocessed/absorbed are never counted as negative.
4. Naming stays pending: name_status == 'pending' everywhere, structure ids are geometric (CTCONS:), no ontology term.
5. Review-only instances (no strict-majority voxels) are listed and not meshed; their ids never appear as parts.
6. The composite carries geometry_qa and composed_geometry_qa for every consensus part (QA separation preserved).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOTE_STATES = {'matched', 'split', 'merge', 'partial', 'seed', 'single', 'voted'}
NO_VOTE_STATES = {'unsupported', 'unprocessed', 'absorbed', 'negative', 'unmatched'}
FIELDS = ('instance_id', 'instance_family', 'role', 'consensus_ml', 'union_ml', 'agreement_ratio', 'unanimous_fraction', 'eligible_models_on_consensus',
          'votes_histogram_on_union', 'conflict_voxels', 'lost_to_other_winner_ml', 'size_class', 'models', 'source_labels', 'candidate_name', 'candidate_evidence',
          'name_status', 'hra_name_by_order', 'hra_z_offset_mm', 'crosses_skellytour_seam_z', 'vote_rule', 'segmentation_models', 'registration_p95_mm')

atlas = json.loads((ROOT / 'public/atlases/ct-consensus.json').read_text())
manifest = {r['source_asset']: r for r in json.loads((ROOT / 'manifests/ct-consensus.json').read_text())}
composed = {p['provenance']['source_asset']: p for p in json.loads((ROOT / 'public/atlases/composed.json').read_text())['parts'] if p['provenance']['source'] == 'ct-consensus'}
tables = {}
bone_report = None
for family, entry in atlas['instance_maps'].items():
    table = json.loads((ROOT / entry['table']).read_text())
    if family == 'bones':
        bone_report = table
        tables[family] = {}
        for cls, e in table['bones'].items():
            if e.get('status') == 'candidate-consensus':
                tables[family][f"B{e['candidate_index']:02d}"] = {**e, 'role': 'bone', 'bone_class': cls, 'source_labels': {m: v['label'] for m, v in e['models'].items() if v['state'] == 'voted'},
                                                                 'lost_to_other_winner_ml': None, 'hra_name_by_order': None, 'hra_z_offset_mm': None, 'crosses_skellytour_seam_z': None}
    else:
        tables[family] = {inst['id']: inst for inst in table['instances']}
nlm_terms = {p['provenance']['label_name']: p['provenance']['structure_id'] for p in json.loads((ROOT / 'public/atlases/nlm-vhf-ct.json').read_text())['parts']}
vox_ml = float(atlas['voxel_spacing_mm'][0] * atlas['voxel_spacing_mm'][1] * atlas['voxel_spacing_mm'][2]) / 1000.0
review_only = {r['id'] for r in atlas['review_only_instances']}
problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


meshed = set()
for part in atlas['parts']:
    prov = part['provenance']
    pid = part['id']
    meshed.add(prov['instance_id'])
    for f in FIELDS:
        check(f in prov, f'{pid}: source atlas lacks {f}')
    check(pid in manifest, f'{pid}: not in manifests/ct-consensus.json')
    check(pid in composed or prov['role'] in ('sacrum', 'bone'), f'{pid}: not in the composite')
    if pid in manifest:
        check(all(manifest[pid].get(f) == prov.get(f) for f in FIELDS), f'{pid}: manifest copy differs from the source atlas')
    if pid in composed:
        cp = composed[pid]['provenance']
        check(all(cp.get(f) == prov.get(f) for f in FIELDS), f'{pid}: composite copy differs from the source atlas')
        check(cp.get('geometry_qa') and cp.get('composed_geometry_qa'), f'{pid}: composite copy lacks geometry_qa / composed_geometry_qa')
        check(cp.get('geometry_qa', {}).get('geometry_sha256') and cp.get('composed_geometry_qa', {}).get('geometry_sha256'), f'{pid}: QA copies lack digests')
    inst = tables.get(prov['instance_family'], {}).get(prov['instance_id'])
    check(inst is not None, f'{pid}: instance {prov["instance_id"]} not in the {prov["instance_family"]} table')
    if inst:
        for f in ('consensus_ml', 'union_ml', 'agreement_ratio', 'unanimous_fraction', 'eligible_models_on_consensus', 'votes_histogram_on_union', 'conflict_voxels',
                  'lost_to_other_winner_ml', 'models', 'source_labels', 'hra_name_by_order', 'hra_z_offset_mm', 'role'):
            if prov['instance_family'] == 'bones' and f in ('role',):
                continue
            check(prov.get(f) == inst.get(f), f'{pid}: {f} differs from the instance table')
        check(prov.get('crosses_skellytour_seam_z') == inst.get('crosses_skellytour_seam_z'), f'{pid}: seam list differs from the instance table')
    c, u = prov['consensus_ml'], prov['union_ml']
    check(c is not None and u is not None and 0 < c <= u, f'{pid}: consensus {c} mL must be positive and not exceed union {u} mL')
    if prov['agreement_ratio'] is None:
        check(u == 0, f'{pid}: agreement_ratio None with union {u} mL')
    else:
        check(0 <= prov['agreement_ratio'] <= 1 and abs(prov['agreement_ratio'] - round(c / u, 3)) <= 0.0015, f'{pid}: agreement_ratio {prov["agreement_ratio"]} != consensus/union {c}/{u}')
    if prov['unanimous_fraction'] is None:
        check(c == 0, f'{pid}: unanimous_fraction None with consensus {c} mL')
    else:
        check(0 <= prov['unanimous_fraction'] <= 1, f'{pid}: unanimous_fraction out of range')
    elig, votes = prov['eligible_models_on_consensus'], prov['votes_histogram_on_union']
    n_c, n_u = sum(elig.values()), sum(votes.values())
    check(abs(n_c * vox_ml - c) <= 0.01 + vox_ml, f'{pid}: eligible histogram total {n_c} voxels != consensus volume {c} mL')
    check(abs(n_u * vox_ml - u) <= 0.01 + vox_ml, f'{pid}: votes histogram total {n_u} voxels != union volume {u} mL')
    check(all(int(k) >= 1 for k in votes), f'{pid}: union voxel with zero votes')
    check(all(int(k) >= 1 for k in elig), f'{pid}: consensus voxel with no eligible model')
    check(0 <= prov['conflict_voxels'] <= n_u, f'{pid}: conflict_voxels outside [0, union]')
    voting, labels = [], {}
    for m, v in prov['models'].items():
        st = v['state']
        check(st in VOTE_STATES | NO_VOTE_STATES, f'{pid}: model {m} state {st} not documented')
        if st in VOTE_STATES:
            check(v.get('label'), f'{pid}: voting model {m} without label')
            voting.append(m)
            labels[m] = v.get('label')
        else:
            check(not v.get('label'), f'{pid}: non-voting model {m} carries a label')
        if st == 'absorbed':
            check(v.get('absorbed_into') and v.get('fraction_of_union', 0) >= 0.5, f'{pid}: absorbed state without target label or below half of the union')
        if st == 'unprocessed':
            check(v.get('processed_fraction', 1) < 0.5, f'{pid}: unprocessed state with processed fraction >= 0.5')
    check(prov['source_labels'] == labels, f'{pid}: source_labels differs from the voting models\' labels')
    check(len(voting) >= 1, f'{pid}: no voting model')
    check(max(int(k) for k in elig) <= len(prov['models']), f'{pid}: more eligible models than models')
    check(prov['name_status'] == 'pending', f'{pid}: name_status {prov["name_status"]} (must stay pending)')
    if prov['instance_family'] == 'bones':
        check(prov.get('review_status') == 'machine-unverified' and prov.get('consensus_status') == 'candidate-consensus', f'{pid}: bone candidate must be machine-unverified candidate-consensus')
        check(prov['structure_id'] == nlm_terms.get(prov['label_name']), f'{pid}: bone candidate structure id {prov["structure_id"]} differs from the nlm-vhf-ct label {prov["label_name"]} ({nlm_terms.get(prov["label_name"])})')
        check(pid not in composed, f'{pid}: bone candidate composed automatically')
        g = prov.get('gates') or {}
        check(all(g.get(k, {}).get('passed') for k in ('class_equivalence', 'geometric_correspondence', 'laterality')), f'{pid}: a gate did not pass')
        check(not g.get('coverage_eligibility', {}).get('truncated') and g.get('coverage_eligibility', {}).get('eligible_models_on_union_majority', 0) >= 2, f'{pid}: coverage gate failed')
        check(prov['agreement_ratio'] >= 0.70 and prov['unanimous_fraction'] >= 0.60, f'{pid}: below the acceptance floor')
        if prov.get('denver_mesh'):
            check(prov.get('versus_denver_mesh') and prov['versus_denver_mesh']['mesh'] == prov['denver_mesh'], f'{pid}: Denver comparison missing')
    else:
        check(prov['structure_id'].startswith('CTCONS:') and prov.get('ontology_term_label') in (None, ''), f'{pid}: consensus instance carries a resolved ontology term or non-geometric id')
    check(prov['candidate_name'] not in (None, '') or prov['role'] == 'sacrum' or prov['candidate_evidence'], f'{pid}: no candidate name and no evidence text')
    check(prov['geometry_type'] == 'automatic_segmentation_consensus' and 'strict majority' in prov['vote_rule'], f'{pid}: geometry_type or vote_rule wording changed')
    check('unsupported' in prov['vote_rule'] and 'negative' in prov['vote_rule'], f'{pid}: vote_rule must state that unsupported/unprocessed/absorbed are kept apart from negative')

check(not (meshed & review_only), f'review-only instances meshed: {sorted(meshed & review_only)}')
for r in atlas['review_only_instances']:
    inst = tables.get(r['family'], {}).get(r['id'])
    check(inst is not None and inst['consensus_ml'] == 0, f'review-only {r["id"]}: instance table shows consensus voxels or is missing')
for family, table in tables.items():
    for iid, inst in table.items():
        if family != 'bones' and inst['role'] in ('vertebra', 'rib', 'sacrum') and inst['consensus_ml'] > 0:
            check(iid in meshed, f'{family} {iid}: has consensus voxels but is not meshed')
instances_meshed = sum(1 for p in atlas['parts'] if p['provenance']['instance_family'] != 'bones')
bones_meshed = sum(1 for p in atlas['parts'] if p['provenance']['instance_family'] == 'bones')
check(len(composed) == 49 and instances_meshed == 50, f'expected 50 instance meshes and 49 composed (sacrum yields to Denver); got {instances_meshed}/{len(composed)}')
if bone_report:
    accepted = sum(1 for e in bone_report['bones'].values() if e.get('status') == 'candidate-consensus')
    check(bones_meshed == accepted, f'{bones_meshed} bone candidates meshed, {accepted} candidate-consensus in the report')
    listed = {r['id'] for r in atlas.get('review_only_bone_candidates', [])}
    others = {cls for cls, e in bone_report['bones'].items() if e.get('status') not in (None, 'excluded', 'candidate-consensus')}
    check(listed == others, f'review-only bone candidates listed {sorted(listed ^ others)} differ from the report')
sacra = [p['id'] for p in atlas['parts'] if p['provenance']['role'] == 'sacrum']
check(all(s not in composed for s in sacra), f'consensus sacrum composed: {sacra}')

if problems:
    for p in problems[:50]:
        print('FAIL', p)
    raise SystemExit(f'{len(problems)} problems')
states = {}
for part in atlas['parts']:
    for m, v in part['provenance']['models'].items():
        states[v['state']] = states.get(v['state'], 0) + 1
print(json.dumps({'meshed_instances': len(atlas['parts']), 'composed_instances': len(composed), 'review_only': len(review_only), 'model_states': states,
                  'pending_names': sum(p['provenance']['name_status'] == 'pending' for p in atlas['parts']), 'copies_equal': True}))
