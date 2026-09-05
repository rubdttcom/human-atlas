"""Inspect BMFToolkit without silently publishing assets with unresolved terms."""
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
from scipy.io import loadmat
import trimesh

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'sources/BMFToolkit'
file = SOURCE / 'data/model_Original.mat'
models = loadmat(file, simplify_cells=True)['model_Original']
revision = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
sha = hashlib.sha256(file.read_bytes()).hexdigest()
records = []
for i, model in enumerate(models):
    name = model['BoneName']
    side = 'right' if name.endswith('R') else 'left' if name.endswith('L') else 'midline'
    mesh = trimesh.Trimesh(vertices=model['vertices_global'], faces=np.asarray(model['faces'], dtype=int) - 1, process=False)
    records.append({'source': 'bmftoolkit', 'source_asset': name, 'mat_index_one_based': i + 1,
                    'source_revision': revision, 'input_sha256': sha, 'source_sex': 'female', 'source_donor': 'VHF',
                    'geometry_type': 'manual_segmentation' if side == 'right' else 'mirrored_from_right',
                    'laterality': side, 'vertices': len(mesh.vertices), 'faces': len(mesh.faces),
                    'bounds_native_metres': mesh.bounds.tolist(), 'watertight': bool(mesh.is_watertight),
                    'landmarks': np.asarray(model['LandmarkNames']).tolist(),
                    'canonical_registration': None, 'included_in_open_build': False,
                    'notes': 'Source neutral-pose correction, smoothing and mirroring; sacrum uses mirrored right half. Asset licence scope pending.',
                    'method_evidence': 'https://arxiv.org/pdf/1804.03655'})
(ROOT / 'generated/bmftoolkit-inventory.json').write_text(json.dumps(records, indent=2) + '\n')
print(json.dumps({'meshes_in_mat': len(records), 'segmented_right': sum(r['laterality'] == 'right' for r in records),
                  'mirrored_or_symmetrized': sum(r['laterality'] != 'right' for r in records), 'published': 0}))
