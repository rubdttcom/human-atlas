"""Geometry identity for QA carry-over: measured results follow a mesh only under a verifiable SHA-256.

`geometry_digest` hashes the exact shipped bytes (float32 vertices, uint32 faces). A previous QA row is
reused only when it carries `geometry_sha256` and that digest equals the digest of the mesh now being
reported. Aggregate statistics (triangle count, edge counts, signed volume) never establish identity:
two different meshes can share all of them (see scripts/test-qa-carryover.py). Rows from reports that
predate the field get their digest from the buffers of the git revision that produced them
(scripts/qa-hash-revision.py), never from statistics.
"""
import hashlib

import numpy as np

CARRIED = ('self_intersections', 'connected_components', 'outlier_components')


def geometry_digest(vertices, faces):
    return hashlib.sha256(np.ascontiguousarray(vertices, dtype='<f4').tobytes() + np.ascontiguousarray(faces, dtype='<u4').tobytes()).hexdigest()


def identical(previous_row, digest):
    """True only when the previous row names the same geometry by SHA-256. No digest, no identity."""
    return bool(previous_row) and previous_row.get('geometry_sha256') == digest


def carry_over(previous_row, record):
    """Copy measured anatomy-QA fields from a previous qa-report row into `record` when the geometry is identical."""
    if not identical(previous_row, record['geometry_sha256']) or previous_row.get('self_intersections', 'not-assessed') == 'not-assessed':
        return False
    record.update({k: previous_row[k] for k in CARRIED if k in previous_row})
    return True


def reusable(previous_entry, digest, recompute=False):
    """Return the previous anatomy-qa entry when it measured exactly this geometry, else None."""
    return previous_entry if not recompute and identical(previous_entry, digest) else None
