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
7. Bone candidates (family `bones`, plan B section 2.6): gates, versus_nlm_vhf_ct_label, versus_denver_mesh, denver_mesh, bone_class,
   label_name, review_status and consensus_status are copied unchanged from generated/ct-bone-consensus-nlm.json into the source atlas and
   the manifest; the gate records are internally consistent (every pair passed, every voting model is class-equivalent, laterality per
   model equals the expected side); the CT-label comparison is mandatory for every candidate and the Denver comparison for every
   candidate with a Denver mesh, both with figures in range. These fields are compared, never recomputed.
8. Shape check of plan B section 2.6 (`shape_check`, scripts/ct-candidate-shape-check.py): mandatory for every bone candidate, bound by
   SHA-256 to the shipped geometry, HU = 300 edge with a 20 mm band, decision in the documented vocabulary, passed flag equal to
   shape p95 <= the Denver baseline figure of generated/denver-ct-baseline.json (or None where no class baseline exists).
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ct_edge_fit import read_part  # noqa: E402
from qa_identity import geometry_digest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VOTE_STATES = {'matched', 'split', 'merge', 'partial', 'seed', 'single', 'voted'}
NO_VOTE_STATES = {'unsupported', 'unprocessed', 'absorbed', 'negative', 'unmatched'}
FIELDS = ('instance_id', 'instance_family', 'role', 'consensus_ml', 'union_ml', 'agreement_ratio', 'unanimous_fraction', 'eligible_models_on_consensus',
          'votes_histogram_on_union', 'conflict_voxels', 'lost_to_other_winner_ml', 'size_class', 'models', 'source_labels', 'candidate_name', 'candidate_evidence',
          'name_status', 'hra_name_by_order', 'hra_z_offset_mm', 'crosses_skellytour_seam_z', 'vote_rule', 'segmentation_models', 'registration_p95_mm', 'posture_offset')
# Bone-candidate fields (plan B 2.6): copied from the bone report and compared between copies; a laxer copy would hide a failed gate or a lost comparison.
BONE_FIELDS = ('gates', 'versus_nlm_vhf_ct_label', 'versus_denver_mesh', 'denver_mesh', 'bone_class', 'label_name', 'review_status', 'consensus_status', 'shape_check')
BONE_TABLE_FIELDS = ('gates', 'versus_nlm_vhf_ct_label', 'versus_denver_mesh', 'denver_mesh', 'bone_class', 'review_status', 'shape_check')
SHAPE_DECISIONS = {'reaches-denver-baseline': True, 'above-denver-baseline': False, 'no-class-baseline': None, 'diverged': None, 'no-ct-edge': None, 'baseline-diverged': None}
GATES = ('class_equivalence', 'geometric_correspondence', 'laterality', 'coverage_eligibility')

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
                                                                 'lost_to_other_winner_ml': None, 'hra_name_by_order': None, 'hra_z_offset_mm': None, 'crosses_skellytour_seam_z': None,
                                                                 'versus_nlm_vhf_ct_label': e.get('versus_nlm_vhf_ct_label'), 'versus_denver_mesh': e.get('versus_denver_mesh'), 'denver_mesh': e.get('denver_mesh'),
                                                                 'shape_check': e.get('shape_check')}
    else:
        tables[family] = {inst['id']: inst for inst in table['instances']}
buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in atlas['chunks']]
_baseline_path = ROOT / 'generated/denver-ct-baseline.json'
baseline_bones = {b['bone']: b for b in json.loads(_baseline_path.read_text())['bones'] if 'own_rigid_fit' in b} if _baseline_path.exists() else {}
nlm_terms = {p['provenance']['label_name']: p['provenance']['structure_id'] for p in json.loads((ROOT / 'public/atlases/nlm-vhf-ct.json').read_text())['parts']}
nlm_atlas = json.loads((ROOT / 'public/atlases/nlm-vhf-ct.json').read_text())
nlm_manifest = {r['source_asset']: r for r in json.loads((ROOT / 'manifests/nlm-vhf-ct.json').read_text())}
composed_nlm = {p['provenance']['source_asset']: p for p in json.loads((ROOT / 'public/atlases/composed.json').read_text())['parts'] if p['provenance']['source'] == 'nlm-vhf-ct'}
# Plan B stage 0: the trunk posture offset report must be the one the meshes carry (hash-bound) and its figures must be copied unchanged.
POSTURE_PATH = ROOT / 'generated/trunk-posture-offset.json'
posture = json.loads(POSTURE_PATH.read_text())
posture_sha = hashlib.sha256(POSTURE_PATH.read_bytes()).hexdigest()
posture_by_id = {**{lv['id']: lv for lv in posture['levels']}, **{k: v for k, v in posture['ribs'].items() if 'centroid_offset_vhf_mm' in v}}
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
    fields = FIELDS + BONE_FIELDS if prov.get('instance_family') == 'bones' else FIELDS
    for f in fields:
        check(f in prov, f'{pid}: source atlas lacks {f}')
    check(pid in manifest, f'{pid}: not in manifests/ct-consensus.json')
    check(pid in composed or prov['role'] in ('sacrum', 'bone'), f'{pid}: not in the composite')
    if pid in manifest:
        for f in fields:
            check(manifest[pid].get(f) == prov.get(f), f'{pid}: manifest copy of {f} differs from the source atlas')
    if pid in composed:
        cp = composed[pid]['provenance']
        for f in fields:
            check(cp.get(f) == prov.get(f), f'{pid}: composite copy of {f} differs from the source atlas')
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
    po = prov.get('posture_offset')
    if prov['instance_family'] == 'bones':
        check(po is None, f'{pid}: bone candidate carries a posture offset (measured only for vertebra, rib and sacrum instances)')
    else:
        check(isinstance(po, dict) and po.get('report_sha256') == posture_sha, f'{pid}: posture_offset missing or bound to another report (plan B stage 0)')
        ref = posture_by_id.get(prov['instance_id'])
        if ref is None:
            check(po.get('status') == 'not-measured', f'{pid}: posture_offset status {po.get("status")} but the report has no entry for {prov["instance_id"]}')
        elif isinstance(po, dict):
            check(po.get('status') == 'measured', f'{pid}: posture_offset status {po.get("status")} although the report measured {prov["instance_id"]}')
            check(po.get('centroid_offset_vhf_mm') == ref['centroid_offset_vhf_mm'], f'{pid}: posture centroid offset differs from the report')
            check(po.get('relative_to_pelvis') == ref.get('relative_to_pelvis'), f'{pid}: posture relative-to-pelvis offset differs from the report')
            check(po.get('discrepancy_threshold') == ref.get('discrepancy_threshold'), f'{pid}: posture discrepancy threshold differs from the report')
            if prov['role'] != 'rib':   # ribs carry no per-model maps, so no model range and no threshold
                check('not an error bound' in ((po.get('discrepancy_threshold') or {}).get('rule') or ''), f'{pid}: discrepancy threshold rule must state it is not an error bound')
            check((po.get('own_rigid_fit') or {}).get('angle_deg') == ref['own_rigid_fit']['angle_deg'], f'{pid}: posture own-fit rotation differs from the report')
            check(po.get('common_shift_vhf_mm') == posture['summary']['common_shift_vhf_mm'], f'{pid}: posture common shift differs from the report')
            note = (po.get('note') or '').lower()
            check('nothing is corrected' in note and 'nothing is anatomy' in note and 'validat' not in note, f'{pid}: posture note must say nothing is corrected and nothing is anatomy, never validation')
            check('not identif' in note or 'identifies the cause of no part' in note, f'{pid}: posture note must say the cause is not identified')
    if prov['instance_family'] == 'bones':
        check(prov.get('review_status') == 'machine-unverified' and prov.get('consensus_status') == 'candidate-consensus', f'{pid}: bone candidate must be machine-unverified candidate-consensus')
        check(prov['structure_id'] == nlm_terms.get(prov['label_name']), f'{pid}: bone candidate structure id {prov["structure_id"]} differs from the nlm-vhf-ct label {prov["label_name"]} ({nlm_terms.get(prov["label_name"])})')
        check(pid not in composed, f'{pid}: bone candidate composed automatically')
        if inst:
            for f in BONE_TABLE_FIELDS:
                check(prov.get(f) == inst.get(f), f'{pid}: {f} differs from the bone report')
            check(prov['label_name'] == inst['source_labels'].get('totalseg'), f'{pid}: label_name {prov["label_name"]} is not the TotalSegmentator label of the report')
        g = prov.get('gates') or {}
        check(isinstance(g, dict) and all(k in g for k in GATES), f'{pid}: gates record incomplete (needs {GATES})')
        check(all(g.get(k, {}).get('passed') is True for k in ('class_equivalence', 'geometric_correspondence', 'laterality')), f'{pid}: a gate did not pass')
        pairs = g.get('geometric_correspondence', {}).get('pairs') or {}
        n_models = len(voting)
        check(len(pairs) == n_models * (n_models - 1) // 2 and n_models >= 2, f'{pid}: geometric correspondence has {len(pairs)} pairs for {n_models} voting models')
        for pair, v in pairs.items():
            check(set(pair.split('|')) <= set(voting) and len(pair.split('|')) == 2, f'{pid}: correspondence pair {pair} names a non-voting model')
            check(v.get('passed') is True and 0 <= v.get('iou_largest_components', -1) <= 1 and v.get('centroid_offset_mm', -1) >= 0,
                  f'{pid}: correspondence pair {pair} did not pass or has figures out of range')
        check(set(voting) <= set(g.get('class_equivalence', {}).get('equivalent_models') or []), f'{pid}: a voting model is not class-equivalent')
        lat = g.get('laterality', {})
        if lat.get('applicable'):
            check(lat.get('expected') == prov['laterality'] and set(lat.get('per_model_side', {})) == set(voting)
                  and all(side == lat.get('expected') for side in lat.get('per_model_side', {}).values()), f'{pid}: laterality gate inconsistent with the voting models or the part laterality')
        else:
            check(prov['laterality'] in (None, '', 'midline', 'bilateral', 'unpaired'), f'{pid}: laterality gate not applicable but part is lateralised ({prov["laterality"]})')
        cov = g.get('coverage_eligibility', {})
        check(cov.get('truncated') is False and cov.get('eligible_models_on_union_majority', 0) >= 2, f'{pid}: coverage gate failed')
        check(0 <= cov.get('fov_edge_contact_fraction_of_surface', -1) <= 1 and 0 <= cov.get('union_outside_coverage_fraction', -1) <= 1, f'{pid}: coverage figures out of range')
        check(prov['agreement_ratio'] >= 0.70 and prov['unanimous_fraction'] >= 0.60, f'{pid}: below the acceptance floor')
        ct = prov.get('versus_nlm_vhf_ct_label')
        check(isinstance(ct, dict) and 0 <= ct.get('dice', -1) <= 1 and ct.get('volume_ratio_candidate_over_label', 0) > 0,
              f'{pid}: comparison against the nlm-vhf-ct label is mandatory and must carry dice in [0, 1] and a positive volume ratio')
        dv = prov.get('versus_denver_mesh')
        if prov.get('denver_mesh'):
            check(isinstance(dv, dict) and dv.get('mesh') == prov['denver_mesh'], f'{pid}: Denver comparison missing or names another mesh')
            for k in ('candidate_surface_to_denver_vertices_mm', 'denver_vertices_to_candidate_surface_mm'):
                d = (dv or {}).get(k) or {}
                check(0 <= d.get('p50', -1) <= d.get('p95', -1), f'{pid}: Denver comparison {k} lacks p50 <= p95')
            check(dv and 'not a substitution decision' in dv.get('note', ''), f'{pid}: Denver comparison note must state it is not a substitution decision')
        else:
            check(dv is None, f'{pid}: Denver comparison recorded without a Denver mesh')
        # shape check of plan B 2.6: mandatory, bound to the shipped geometry, decision from the documented vocabulary and consistent with the figures
        sc = prov.get('shape_check')
        check(isinstance(sc, dict), f'{pid}: shape_check missing (plan B 2.6 shape check not run; the candidate is not acceptable without it)')
        if isinstance(sc, dict):
            check(sc.get('decision') in SHAPE_DECISIONS and sc.get('passed') == SHAPE_DECISIONS.get(sc.get('decision')), f'{pid}: shape_check decision {sc.get("decision")} / passed {sc.get("passed")} inconsistent')
            check(sc.get('hu_edge') == 300 and sc.get('band_mm') == 20, f'{pid}: shape_check reference is not the HU = 300 edge with a 20 mm band')
            digest = geometry_digest(*read_part(buffers, part))
            check(sc.get('geometry_sha256') == digest, f'{pid}: shape_check is bound to another geometry ({sc.get("geometry_sha256")} != shipped {digest})')
            if sc.get('decision') in ('reaches-denver-baseline', 'above-denver-baseline'):
                check(sc.get('baseline_bone') and sc.get('baseline_shape_p95_mm') is not None and sc.get('shape_p95_mm') is not None
                      and (sc['shape_p95_mm'] <= sc['baseline_shape_p95_mm']) == sc['passed'], f'{pid}: shape_check passed flag does not follow shape p95 versus the baseline')
                check(sc.get('diverged') is False, f'{pid}: shape_check compared to the baseline although the fit diverged')
                base = baseline_bones.get(sc.get('baseline_bone'))
                check(base is not None and base['own_rigid_fit']['shape_residual']['p95_mm'] == sc['baseline_shape_p95_mm'], f'{pid}: baseline figure differs from generated/denver-ct-baseline.json')
            if sc.get('decision') == 'no-class-baseline':
                check(sc.get('baseline_bone') is None and prov['denver_mesh'] is None, f'{pid}: no-class-baseline recorded although a Denver bone or mesh exists')
            if sc.get('shape_p95_mm') is not None:
                check(0 <= sc['shape_p95_mm'] and 0 <= sc.get('placement_p95_mm', -1), f'{pid}: shape_check figures out of range')
            check('not anatomical validation' in sc.get('note', '') or 'no acceptance' in sc.get('note', '') or sc.get('passed') is None, f'{pid}: shape_check note must not read as validation')
    else:
        check(prov['structure_id'].startswith('CTCONS:') and prov.get('ontology_term_label') in (None, ''), f'{pid}: consensus instance carries a resolved ontology term or non-geometric id')
    check(prov['candidate_name'] not in (None, '') or prov['role'] == 'sacrum' or prov['candidate_evidence'], f'{pid}: no candidate name and no evidence text')
    check(prov['geometry_type'] == 'automatic_segmentation_consensus' and 'strict majority' in prov['vote_rule'], f'{pid}: geometry_type or vote_rule wording changed')
    check('unsupported' in prov['vote_rule'] and 'negative' in prov['vote_rule'], f'{pid}: vote_rule must state that unsupported/unprocessed/absorbed are kept apart from negative')

# nlm-vhf-ct meshes carry the same measurement as context (trunk_posture_context), hash-bound and copied unchanged to manifest and composite.
for part in nlm_atlas['parts']:
    prov = part['provenance']
    pid = part['id']
    ctx = prov.get('trunk_posture_context')
    check(isinstance(ctx, dict) and ctx.get('report_sha256') == posture_sha, f'{pid}: trunk_posture_context missing or bound to another report')
    if isinstance(ctx, dict):
        ref = posture_by_id.get(ctx.get('instance_id'))
        check(ref is not None, f'{pid}: trunk_posture_context points to an unmeasured instance {ctx.get("instance_id")}')
        if ref:
            check(ctx.get('centroid_offset_vhf_mm') == ref['centroid_offset_vhf_mm'] and ctx.get('relative_to_pelvis') == ref.get('relative_to_pelvis'), f'{pid}: trunk_posture_context figures differ from the report')
            check(ctx.get('own_rigid_fit_angle_deg') == ref['own_rigid_fit']['angle_deg'], f'{pid}: trunk_posture_context rotation differs from the report')
        label = prov.get('label_name', '')
        voted = sorted(iid for fam, tb in tables.items() if fam != 'bones' for iid, inst in tb.items() if inst.get('consensus_ml', 0) > 0 and inst['source_labels'].get('totalseg') == label)
        check(sorted(ctx.get('linked_instance_ids') or []) == voted, f'{pid}: linked_instance_ids {ctx.get("linked_instance_ids")} differ from the instances the label voted into {voted} (a split label must keep every instance)')
        if voted:
            check(ctx.get('instance_id') in voted and ctx.get('link', '').startswith('label voted into'), f'{pid}: {label} voted into {voted} but the context uses {ctx.get("instance_id")} / {ctx.get("link")}')
            if len(voted) > 1:
                z = ctx.get('mesh_centroid_z_vhf_mm')
                nearest = min(voted, key=lambda i: abs(posture_by_id[i]['nlm_centroid'][2] - z)) if all(i in posture_by_id and 'nlm_centroid' in posture_by_id[i] for i in voted) else None
                check(nearest is None or ctx.get('instance_id') == nearest, f'{pid}: split label figures must come from the linked instance nearest in z ({nearest}), got {ctx.get("instance_id")}')
                check(sorted(l['id'] for l in (ctx.get('linked_levels') or [])) == voted, f'{pid}: linked_levels must list every linked instance')
        else:
            check(ctx.get('link', '').startswith('nearest measured vertebral level'), f'{pid}: label voted into no instance but link is {ctx.get("link")}')
        check('nothing is corrected' in (ctx.get('note') or '').lower() and 'validat' not in (ctx.get('note') or '').lower(), f'{pid}: trunk_posture_context note wording')
    if pid in nlm_manifest:
        check(nlm_manifest[pid].get('trunk_posture_context') == ctx, f'{pid}: manifest copy of trunk_posture_context differs')
    if pid in composed_nlm:
        check(composed_nlm[pid]['provenance'].get('trunk_posture_context') == ctx, f'{pid}: composite copy of trunk_posture_context differs')

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
                  'pending_names': sum(p['provenance']['name_status'] == 'pending' for p in atlas['parts']), 'copies_equal': True,
                  'posture_measured': sum((p['provenance'].get('posture_offset') or {}).get('status') == 'measured' for p in atlas['parts']), 'nlm_meshes_with_posture_context': sum('trunk_posture_context' in p['provenance'] for p in nlm_atlas['parts'])}))
