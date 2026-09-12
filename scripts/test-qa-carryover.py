"""Regression test: QA carry-over must never follow aggregate statistics, only a matching geometry_sha256.

Usage: python scripts/test-qa-carryover.py            (seconds; exits non-zero on any failure)

Case from the b0063fd/083589a review: two disconnected closed boxes (main side 0.03125 m, secondary side
0.015625 m). Moving the secondary box from x = 0.03125 m to x = 0.125 m leaves triangle count, degenerate
faces, boundary and nonmanifold edge counts and signed volume exactly equal (a closed component's volume is
translation-invariant) while the outlier test flips from 0 to 1 at OUTLIER_MM = 60. A fingerprint on those
statistics would carry the stale `outlier_components = 0` onto the new geometry; the digest must not.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_identity import carry_over, geometry_digest, identical, reusable  # noqa: E402

FINGERPRINT = ('triangles', 'degenerate_faces', 'boundary_edges', 'nonmanifold_edges', 'signed_volume_m3')


def box(centre, side):
    c = np.array(centre, dtype=np.float32)
    corners = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=np.float32) * (side / 2) + c
    faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], dtype=np.uint32)
    return corners, faces


def scene(secondary_x):
    v1, f1 = box((0, 0, 0), 0.03125)
    v2, f2 = box((secondary_x, 0, 0), 0.015625)
    return np.vstack([v1, v2]).astype(np.float32), np.vstack([f1, f2 + len(v1)]).astype(np.uint32)


def statistics(vertices, faces):
    fv = vertices[faces].astype(float)
    cross = np.cross(fv[:, 1] - fv[:, 0], fv[:, 2] - fv[:, 0])
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return {'triangles': len(faces), 'degenerate_faces': int(np.count_nonzero(np.linalg.norm(cross, axis=1) / 2 < 1e-14)),
            'boundary_edges': int(np.count_nonzero(counts == 1)), 'nonmanifold_edges': int(np.count_nonzero(counts > 2)),
            'signed_volume_m3': float(np.einsum('ij,ij->i', fv[:, 0], cross).sum() / 6)}


def main():
    before, after = scene(0.03125), scene(0.125)
    stats_before, stats_after = statistics(*before), statistics(*after)
    assert all(stats_before[k] == stats_after[k] for k in FINGERPRINT), 'the test case must share every fingerprint field'
    digest_before, digest_after = geometry_digest(*before), geometry_digest(*after)
    assert digest_before != digest_after
    # A measured row for the old geometry, as qa-anatomy writes it into qa-report.
    old_row = {'atlas': 't', 'structure': 'boxes', **stats_before, 'geometry_sha256': digest_before,
               'self_intersections': '0 intersecting triangle pairs (Moller test; 0 coplanar candidates not resolved)', 'connected_components': 2, 'outlier_components': 0}
    new_record = {'atlas': 't', 'structure': 'boxes', **stats_after, 'geometry_sha256': digest_after, 'self_intersections': 'not-assessed'}
    assert not carry_over(old_row, new_record) and new_record['self_intersections'] == 'not-assessed' and 'outlier_components' not in new_record, 'fingerprint-equal geometry must not be carried over'
    same_record = {'atlas': 't', 'structure': 'boxes', **stats_before, 'geometry_sha256': digest_before, 'self_intersections': 'not-assessed'}
    assert carry_over(old_row, same_record) and same_record['outlier_components'] == 0 and same_record['connected_components'] == 2
    legacy_row = {k: v for k, v in old_row.items() if k != 'geometry_sha256'}
    assert not carry_over(legacy_row, dict(same_record, self_intersections='not-assessed')), 'a row without a digest is never carried over, even for identical geometry'
    assert not carry_over(None, dict(same_record)) and not identical(None, digest_before)
    unassessed = dict(old_row, self_intersections='not-assessed')
    assert not carry_over(unassessed, dict(same_record)), 'not-assessed rows carry nothing'
    # anatomy-qa entries: reuse follows the same rule.
    old_entry = {'atlas': 't', 'structure': 'boxes', 'geometry_sha256': digest_before, 'triangles': 24, 'self_intersecting_pairs': 0, 'components': 2, 'outlier_components': []}
    assert reusable(old_entry, digest_before) is old_entry and reusable(old_entry, digest_after) is None
    assert reusable({k: v for k, v in old_entry.items() if k != 'geometry_sha256'}, digest_before) is None and reusable(old_entry, digest_before, recompute=True) is None
    print(json.dumps({'fingerprint_equal': True, 'digests_differ': True, 'carry_over_blocked': True, 'legacy_row_blocked': True, 'identical_geometry_reused': True}))


if __name__ == '__main__':
    main()
