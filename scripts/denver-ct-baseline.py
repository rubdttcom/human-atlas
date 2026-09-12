"""Baseline for the plan B bone-concordance criterion: Denver bones against the cortical edge of the same-donor CT.

Reference and procedure, identical for Denver bones today and for machine bones later:
  1. The Denver bone (VHF-image-2022 frame) is carried into the CT frame with the inverse of nlm-ct-to-vhf
     (global placement) and the residual to the CT cortical edge is measured: "placement" distances.
  2. The bone is then fitted rigidly on its own (ICP, no scale) to the CT cortical edge within its own
     neighbourhood: "shape" distances. Placement and shape are reported separately.
  The CT cortical edge is the iso-surface HU = 300 of the fresh CT, extracted only inside a 20 mm band
  around the bone so that the fit cannot latch onto other bones. Distances are bone surface -> CT edge
  (one direction), because the band contains edges of neighbouring bones. Points whose nearest CT voxel
  lies outside the acquired field of view (data/derived/nlm-vhf/ct-coverage-mask.nii.gz) are excluded.

Output: generated/denver-ct-baseline.json (per bone: placement p95, shape p95, rotation of the own fit).
The procedure lives in scripts/ct_edge_fit.py and is shared with scripts/ct-candidate-shape-check.py (same reference, same code).
"""
import json
from pathlib import Path
import numpy as np
from ct_edge_fit import ROOT, HU_EDGE, BAND_MM, EdgeFit, read_part

FIT = EdgeFit(seed=1993)
denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in denver['chunks']]
cover = FIT.cover

def denver_bone(part):
    v, f = read_part(buffers, part)
    return FIT.stage_mesh_to_ct(v, f)   # -> CT RAS mm

report = {'method': __doc__.strip(), 'hu_edge': HU_EDGE, 'band_mm': BAND_MM, 'coverage_mask_used': cover is not None, 'bones': []}
bones = [p for p in denver['parts'] if p['source_metadata']['tissue_class'] == 'Bone']
for part in sorted(bones, key=lambda p: (p['source_metadata']['source_label'], p['source_metadata']['source_folder'])):
    name = f"{part['source_metadata']['source_label']}_{part['source_metadata']['source_folder']}"
    mesh = denver_bone(part)
    fit = FIT.fit(mesh)
    if fit is None:
        report['bones'].append({'bone': name, 'status': 'no CT cortical edge in band (outside field of view or below HU threshold)'}); print(name, 'no edge'); continue
    placement, own = fit['placement_under_nlm_ct_to_vhf'], fit['own_rigid_fit']
    rot, disp, shape, diverged = own['rotation_deg'], own['centroid_displacement_mm'], own['shape_residual'], own['diverged']
    entry = {'bone': name, 'denver_id': part['id'], 'denver_volume_cm3': float(abs(mesh.volume) / 1000), 'ct_edge_points': fit['ct_edge_points'],
             'placement_under_nlm_ct_to_vhf': placement, 'own_rigid_fit': own}
    report['bones'].append(entry)
    print(f"{name:26s} placement p95 {placement['p95_mm']:5.2f} mm | own rigid: rot {rot:4.1f} deg, centroid shift {disp:5.1f} mm, shape p95 {shape['p95_mm']:5.2f} mm{'  DIVERGED' if diverged else ''}", flush=True)
ok = [b for b in report['bones'] if 'own_rigid_fit' in b and not b['own_rigid_fit']['diverged']]
report['summary'] = {'bones_measured': len(ok), 'bones_diverged': [b['bone'] for b in report['bones'] if b.get('own_rigid_fit', {}).get('diverged')], 'shape_p95_mm_median': float(np.median([b['own_rigid_fit']['shape_residual']['p95_mm'] for b in ok])),
                     'shape_p95_mm_max': float(max(b['own_rigid_fit']['shape_residual']['p95_mm'] for b in ok)),
                     'placement_p95_mm_median': float(np.median([b['placement_under_nlm_ct_to_vhf']['p95_mm'] for b in ok]))}
(ROOT / 'generated/denver-ct-baseline.json').write_text(json.dumps(report, indent=1) + '\n')
print(json.dumps(report['summary'], indent=1))
