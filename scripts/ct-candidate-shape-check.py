"""Per-bone shape check of plan B section 2.6 for the machine bone candidates of source `ct-consensus` (family `bones`).

Usage: .venv/bin/python scripts/ct-candidate-shape-check.py nlm

Same reference and same code as the Denver baseline (scripts/ct_edge_fit.py, scripts/denver-ct-baseline.py): the shipped
candidate mesh is carried into the CT frame, its residual to the HU = 300 cortical edge is measured as placed
("placement", registration and posture included) and after its own rigid fit ("shape"). The criterion of section 2.6 is
shape p95 <= the shape p95 Denver's bone of the same class and side reaches with this procedure
(generated/denver-ct-baseline.json). Classes Denver does not cover (clavicles, scapulae, skull, sternum) have no baseline:
their figures are reported against the overall Denver median and maximum for information and the decision stays
`no-class-baseline`; nothing is accepted on that basis.

Writes generated/ct-candidate-shape-check-nlm.json and adds a `shape_check` record to each candidate-consensus entry of
generated/ct-bone-consensus-nlm.json (bound to the SHA-256 of the shipped geometry, scripts/qa_identity.py). Nothing here
is anatomical validation: a segmentation surface close to an intensity iso-surface is still a machine label.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ct_edge_fit import ROOT, HU_EDGE, BAND_MM, EdgeFit, read_part  # noqa: E402
from qa_identity import geometry_digest  # noqa: E402

CT = sys.argv[1] if len(sys.argv) > 1 else 'nlm'
if CT != 'nlm':
    raise SystemExit('only the NLM fresh CT has a Denver baseline today')
BASELINE_CLASS = {'femur_left': 'Femur_Left', 'femur_right': 'Femur_Right', 'hip_left': 'Pelvis_Left', 'hip_right': 'Pelvis_Right',
                  'tibia_left': 'Tibia_Left', 'tibia_right': 'Tibia_Right', 'fibula_left': 'Fibula_Left', 'fibula_right': 'Fibula_Right',
                  'patella_left': 'Patella_Left', 'patella_right': 'Patella_Right', 'sacrum': 'Sacrum_Left'}

atlas_path = ROOT / 'public/atlases/ct-consensus.json'
atlas = json.loads(atlas_path.read_text())
buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in atlas['chunks']]
report_path = ROOT / atlas['instance_maps']['bones']['table']
bone_report = json.loads(report_path.read_text())
baseline = json.loads((ROOT / 'generated/denver-ct-baseline.json').read_text())
base_by_name = {b['bone']: b for b in baseline['bones'] if 'own_rigid_fit' in b}
fit = EdgeFit(seed=1993)

out = {'method': __doc__.strip(), 'ct': CT, 'hu_edge': HU_EDGE, 'band_mm': BAND_MM, 'coverage_mask_used': fit.cover is not None,
       'baseline': {'file': 'generated/denver-ct-baseline.json', 'shape_p95_mm_median': baseline['summary']['shape_p95_mm_median'],
                    'shape_p95_mm_max': baseline['summary']['shape_p95_mm_max'], 'bones_measured': baseline['summary']['bones_measured']},
       'candidates': []}
parts = [p for p in atlas['parts'] if p['provenance']['instance_family'] == 'bones']
for part in sorted(parts, key=lambda p: p['provenance']['instance_index']):
    prov = part['provenance']
    v, f = read_part(buffers, part)
    digest = geometry_digest(v, f)
    mesh = fit.stage_mesh_to_ct(v, f)
    cls = prov['bone_class']
    base_name = BASELINE_CLASS.get(cls)
    base = base_by_name.get(base_name) if base_name else None
    entry = {'instance_id': prov['instance_id'], 'part_id': part['id'], 'bone_class': cls, 'geometry_sha256': digest, 'candidate_volume_cm3': float(abs(mesh.volume) / 1000),
             'baseline_bone': base_name, 'baseline_shape_p95_mm': base['own_rigid_fit']['shape_residual']['p95_mm'] if base else None,
             'baseline_placement_p95_mm': base['placement_under_nlm_ct_to_vhf']['p95_mm'] if base else None}
    res = fit.fit(mesh)
    if res is None:
        entry.update({'decision': 'no-ct-edge', 'passed': None, 'note': 'no CT cortical edge inside the band (outside the field of view or below the HU threshold)'})
    else:
        entry.update(res)
        shape_p95 = res['own_rigid_fit']['shape_residual']['p95_mm']
        if res['own_rigid_fit']['diverged']:
            entry.update({'decision': 'diverged', 'passed': None, 'note': 'own rigid fit rotated or shifted beyond the divergence limits; shape figure not usable'})
        elif base is None:
            entry.update({'decision': 'no-class-baseline', 'passed': None,
                          'note': f"Denver has no {cls} (pelvis to feet only): shape p95 {shape_p95:.2f} mm versus the overall Denver median {baseline['summary']['shape_p95_mm_median']:.2f} mm and maximum {baseline['summary']['shape_p95_mm_max']:.2f} mm, for information; no acceptance without a class baseline"})
        elif base_name and base_name not in base_by_name:
            entry.update({'decision': 'baseline-diverged', 'passed': None, 'note': 'the Denver bone of this class has no usable shape baseline'})
        else:
            passed = bool(shape_p95 <= entry['baseline_shape_p95_mm'])
            entry.update({'decision': 'reaches-denver-baseline' if passed else 'above-denver-baseline', 'passed': passed,
                          'note': f"shape p95 {shape_p95:.2f} mm versus Denver {base_name} {entry['baseline_shape_p95_mm']:.2f} mm with the same procedure; shape only (posture removed by the per-bone fit); not anatomical validation"})
    out['candidates'].append(entry)
    pl = entry.get('placement_under_nlm_ct_to_vhf', {}).get('p95_mm')
    sh = entry.get('own_rigid_fit', {}).get('shape_residual', {}).get('p95_mm')
    print(f"{prov['instance_id']} {cls:14s} placement p95 {pl if pl is None else round(pl, 2)} | shape p95 {sh if sh is None else round(sh, 2)} | baseline {entry['baseline_shape_p95_mm']} -> {entry['decision']}", flush=True)

# bind the result to the bone report so that ingestion carries it into the provenance
for e in out['candidates']:
    rep = bone_report['bones'][e['bone_class']]
    rep['shape_check'] = {'geometry_sha256': e['geometry_sha256'], 'hu_edge': HU_EDGE, 'band_mm': BAND_MM, 'decision': e['decision'], 'passed': e['passed'],
                          'placement_p95_mm': e.get('placement_under_nlm_ct_to_vhf', {}).get('p95_mm'),
                          'shape_p95_mm': e.get('own_rigid_fit', {}).get('shape_residual', {}).get('p95_mm'),
                          'own_fit_rotation_deg': e.get('own_rigid_fit', {}).get('rotation_deg'), 'own_fit_centroid_displacement_mm': e.get('own_rigid_fit', {}).get('centroid_displacement_mm'),
                          'diverged': e.get('own_rigid_fit', {}).get('diverged'), 'baseline_bone': e['baseline_bone'], 'baseline_shape_p95_mm': e['baseline_shape_p95_mm'],
                          'report': 'generated/ct-candidate-shape-check-nlm.json', 'note': e['note']}
bone_report['shape_check'] = {'report': 'generated/ct-candidate-shape-check-nlm.json', 'baseline': 'generated/denver-ct-baseline.json', 'procedure': 'scripts/ct_edge_fit.py',
                              'decisions': {e['instance_id']: e['decision'] for e in out['candidates']}}
out['summary'] = {'candidates': len(out['candidates']), 'decisions': {d: sum(1 for e in out['candidates'] if e['decision'] == d) for d in sorted({e['decision'] for e in out['candidates']})},
                  'shape_p95_mm': {e['instance_id']: e.get('own_rigid_fit', {}).get('shape_residual', {}).get('p95_mm') for e in out['candidates']}}
(ROOT / 'generated/ct-candidate-shape-check-nlm.json').write_text(json.dumps(out, indent=1) + '\n')
report_path.write_text(json.dumps(bone_report, indent=1) + '\n')
print(json.dumps(out['summary']))
