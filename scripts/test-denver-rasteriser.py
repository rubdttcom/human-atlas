"""Analytic tests of the even-odd rasteriser of scripts/denver-surface-floor.py (Codex audit of 8a5da4b): one box, two disjoint
boxes, a box with a hole (nested shells), two overlapping shells (XOR by convention, documented), and the refusal of an open
contour. Volumes are compared with the analytic voxel counts on integer slice planes.

  .venv/bin/python scripts/test-denver-rasteriser.py
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dsf', ROOT / 'scripts/denver-surface-floor.py')
D = importlib.util.module_from_spec(spec); spec.loader.exec_module(D)
results = {}


def case(name, ok):
    results[name] = bool(ok)
    if not ok:
        print('FAILED', name)


def box(lo, hi):
    lo, hi = np.array(lo, float), np.array(hi, float)
    return trimesh.creation.box(extents=hi - lo, transform=trimesh.transformations.translation_matrix((lo + hi) / 2))


SHAPE = (40, 40, 30)


def pixels_inside(lo, hi):
    """Analytic count of pixel centres (integer i, j) strictly inside [lo, hi) per slice, times the integer k planes cut."""
    ni = len([i for i in range(SHAPE[0]) if lo[0] < i < hi[0]])
    nj = len([j for j in range(SHAPE[1]) if lo[1] < j < hi[1]])
    nk = len([k for k in range(SHAPE[2]) if lo[2] < k < hi[2]])
    return ni * nj * nk


# 1. one box with half-integer faces (no pixel centre on a face)
b1 = box((4.5, 6.5, 2.5), (20.5, 30.5, 12.5))
v, f = D.voxelise(b1, SHAPE)
case('one_box_count', f == 0 and int(v.sum()) == pixels_inside((4.5, 6.5, 2.5), (20.5, 30.5, 12.5)))

# 2. two disjoint boxes add
b2 = trimesh.util.concatenate([box((2.5, 2.5, 2.5), (10.5, 10.5, 8.5)), box((20.5, 20.5, 2.5), (30.5, 30.5, 8.5))])
v, f = D.voxelise(b2, SHAPE)
case('disjoint_boxes_add', f == 0 and int(v.sum()) == pixels_inside((2.5, 2.5, 2.5), (10.5, 10.5, 8.5)) + pixels_inside((20.5, 20.5, 2.5), (30.5, 30.5, 8.5)))

# 3. nested shells: outer box with an inner box (inverted normals) = a hole
inner = box((10.5, 10.5, 2.5), (20.5, 20.5, 12.5)); inner.invert()
b3 = trimesh.util.concatenate([box((4.5, 4.5, 0.5), (30.5, 30.5, 14.5)), inner])
v, f = D.voxelise(b3, SHAPE)
expect = pixels_inside((4.5, 4.5, 0.5), (30.5, 30.5, 14.5)) - pixels_inside((10.5, 10.5, 2.5), (20.5, 20.5, 12.5))
case('nested_shell_is_a_hole', f == 0 and int(v.sum()) == expect)
case('hole_is_empty_inside', not v[15, 15, 6] and v[6, 6, 6])

# 4. overlapping shells: XOR by convention (documented; Denver structures are single shells)
b4 = trimesh.util.concatenate([box((2.5, 2.5, 2.5), (20.5, 20.5, 8.5)), box((10.5, 10.5, 2.5), (30.5, 30.5, 8.5))])
v, f = D.voxelise(b4, SHAPE)
a = pixels_inside((2.5, 2.5, 2.5), (20.5, 20.5, 8.5)); b = pixels_inside((10.5, 10.5, 2.5), (30.5, 30.5, 8.5)); ov = pixels_inside((10.5, 10.5, 2.5), (20.5, 20.5, 8.5))
case('overlap_is_xor_by_convention', f == 0 and int(v.sum()) == a + b - 2 * ov)

# 5. an open contour (a mesh with a missing face) must raise, never leave an empty slice
b5 = box((4.5, 4.5, 2.5), (20.5, 20.5, 12.5))
side = np.where(b5.face_normals[:, 0] > 0.9)[0]       # the two triangles of the +i side face: every integer-k section becomes an open polyline
faces = np.delete(b5.faces, side, axis=0)
b5o = trimesh.Trimesh(b5.vertices, faces, process=False)
try:
    D.voxelise(b5o, SHAPE); case('open_contour_raises', False)
except RuntimeError:
    case('open_contour_raises', True)

ok = all(results.values())
print(json.dumps({'cases': len(results), 'all_as_expected': ok, 'failed': [k for k, v in results.items() if not v]}))
sys.exit(0 if ok else 1)
