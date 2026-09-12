"""Shared procedure of the plan B bone-concordance criterion: a bone surface against the cortical edge of the same-donor CT.

Used by scripts/denver-ct-baseline.py (Denver bones, the baseline) and scripts/ct-candidate-shape-check.py (machine
bone candidates). The criterion requires the same reference and the same code for both, so the code lives here once.

Reference: the iso-surface HU = 300 of the NLM fresh CT, extracted only inside a 20 mm band around the bone so that the
fit cannot latch onto other bones; edge points whose nearest CT voxel lies outside the acquired field of view
(data/derived/nlm-vhf/ct-coverage-mask.nii.gz) are excluded. Distances are bone surface -> CT edge (one direction).
  placement: residual of the bone as placed in the CT frame (inverse of nlm-ct-to-vhf for stage meshes).
  shape: residual after a per-bone rigid ICP (no scale) anchored at the bone centroid, two stages (8 mm then 4 mm band).
Both figures are surface distances of similar things (a segmentation surface to an intensity iso-surface); they are not
anatomical validation and a small residual does not make the label a correct bone.
"""
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1]
HU_EDGE, BAND_MM = 300, 20
FIT_BANDS_MM = (8.0, 4.0)
DIVERGED_ROTATION_DEG, DIVERGED_SHIFT_MM = 15, 15


class EdgeFit:
    def __init__(self, seed=1993):
        self.rng = np.random.default_rng(seed)
        d = ROOT / 'data/derived/nlm-vhf'
        img = nib.load(d / 'vhf-fresh-ct.nii.gz')
        self.ct = np.asanyarray(img.dataobj)
        self.aff = img.affine
        self.inv = np.linalg.inv(self.aff)
        cover_path = d / 'ct-coverage-mask.nii.gz'
        self.cover = np.asanyarray(nib.load(cover_path).dataobj) if cover_path.exists() else None
        stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
        self.stage_to_image = np.linalg.inv(np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4))
        self.ct_to_vhf = np.array(json.loads((ROOT / 'transforms/nlm-ct-to-vhf.json').read_text())['matrix_row_major']).reshape(4, 4)
        self.vhf_to_ct = np.linalg.inv(self.ct_to_vhf)

    def stage_mesh_to_ct(self, vertices, faces):
        """A shipped mesh in the canonical stage (metres) -> CT RAS mm, through VHF-image-2022 and the inverse of nlm-ct-to-vhf."""
        v = trimesh.transform_points(trimesh.transform_points(np.asarray(vertices, dtype=float), self.stage_to_image), self.vhf_to_ct)
        return trimesh.Trimesh(v, np.asarray(faces).reshape(-1, 3), process=False)

    def ct_edge_points(self, mesh):
        lo = nib.affines.apply_affine(self.inv, mesh.bounds[0] - BAND_MM); hi = nib.affines.apply_affine(self.inv, mesh.bounds[1] + BAND_MM)
        lo, hi = np.floor(np.minimum(lo, hi)).astype(int), np.ceil(np.maximum(lo, hi)).astype(int)
        lo = np.clip(lo, 0, np.array(self.ct.shape) - 1); hi = np.clip(hi, 0, np.array(self.ct.shape) - 1)
        box = tuple(slice(a, b + 1) for a, b in zip(lo, hi))
        crop = self.ct[box].astype(np.float32)
        if (crop > HU_EDGE).sum() < 50:
            return None, None
        v, f, _, _ = marching_cubes(crop, HU_EDGE)
        v = nib.affines.apply_affine(self.aff, v + lo)
        edge = trimesh.Trimesh(v, f, process=False)
        d = cKDTree(mesh.vertices).query(edge.vertices)[0]
        keep = edge.vertices[d <= BAND_MM]
        if self.cover is not None and len(keep):
            ijk = np.round(nib.affines.apply_affine(self.inv, keep)).astype(int)
            ijk = np.clip(ijk, 0, np.array(self.ct.shape) - 1)
            keep = keep[self.cover[tuple(ijk.T)] > 0]
        return keep, edge

    def sample(self, mesh, n=30000):
        pts, _ = trimesh.sample.sample_surface(mesh, n, seed=int(self.rng.integers(1 << 31)))
        return np.vstack([pts, mesh.vertices])

    @staticmethod
    def stats(d):
        return {'mean_mm': float(d.mean()), 'rms_mm': float(np.sqrt(np.mean(d ** 2))), 'p95_mm': float(np.quantile(d, .95)), 'max_mm': float(d.max()), 'n': int(len(d))}

    def fit(self, mesh):
        """Placement and own-rigid-fit shape residuals of `mesh` (CT RAS mm). None when the band holds no usable CT edge."""
        edge_pts, _ = self.ct_edge_points(mesh)
        if edge_pts is None or len(edge_pts) < 200:
            return None
        tree = cKDTree(edge_pts)
        src = self.sample(mesh)
        placement = self.stats(tree.query(src)[0])
        centre = src.mean(axis=0)
        matrix = np.eye(4); moved = src
        for band in FIT_BANDS_MM:
            near = edge_pts[cKDTree(moved).query(edge_pts)[0] <= band]
            if len(near) < 200:
                break
            m, _, _ = trimesh.registration.icp(moved - centre, near - centre, initial=np.eye(4), scale=False, max_iterations=40, threshold=1e-7)
            step = np.eye(4); step[:3, :3] = m[:3, :3]; step[:3, 3] = m[:3, 3] + centre - m[:3, :3] @ centre
            matrix = step @ matrix; moved = trimesh.transform_points(src, matrix)
        shape = self.stats(tree.query(moved)[0])
        rot = float(np.degrees(np.arccos(np.clip((np.trace(matrix[:3, :3]) - 1) / 2, -1, 1))))
        disp = float(np.linalg.norm(moved.mean(axis=0) - centre))
        return {'ct_edge_points': int(len(edge_pts)), 'placement_under_nlm_ct_to_vhf': placement,
                'own_rigid_fit': {'rotation_deg': rot, 'centroid_displacement_mm': disp, 'shape_residual': shape,
                                  'diverged': rot > DIVERGED_ROTATION_DEG or disp > DIVERGED_SHIFT_MM}}


def read_part(buffers, part):
    """Vertices (float32, stage metres) and faces (uint32) of a shipped atlas part."""
    data = buffers[part['chunk']]
    v = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3)
    f = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3)
    return v, f
