"""Field-of-view coverage of the NLM VHF fresh CT and body truncation per slice.

The assembled CT (data/derived/nlm-vhf/vhf-fresh-ct.nii.gz) was resampled onto a 480 mm field of view.
The scanner used smaller fields of view for the head (250, 370, 440 mm; see the metadata segments), and
even at 480 mm the body can touch the edge (the arms lie beside the trunk). Outside the acquired field
of view the volume holds padding (-1000 HU), which is not anatomy. Any pipeline that uses the CT as a
prior must treat those voxels as unknown, not as air, and must not clip photograph-derived structures
against a CT mask there.

Outputs
  data/derived/nlm-vhf/ct-coverage-mask.nii.gz  uint8: 1 = inside the acquired field of view of that slice
  generated/nlm-ct-coverage.json                 per-slice field of view and body-truncation report
"""
import json
from pathlib import Path
import nibabel as nib
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'data/derived/nlm-vhf'
meta = json.loads((D / 'vhf-fresh-ct-metadata.json').read_text())
img = nib.load(D / 'vhf-fresh-ct.nii.gz')
ct = np.asanyarray(img.dataobj)
nx, ny, nz = ct.shape
sx, sy, sz = img.header.get_zooms()
# in-plane radius from the image centre, mm
cx, cy = (nx - 1) / 2, (ny - 1) / 2
yy, xx = np.meshgrid((np.arange(ny) - cy) * sy, (np.arange(nx) - cx) * sx, indexing='ij')
rr = np.sqrt(xx ** 2 + yy ** 2).T   # shape (nx, ny)
fov_per_slice = np.full(nz, 480.0)
for seg in meta['segments']:
    fov_per_slice[seg['first_index']:seg['last_index'] + 1] = seg['fov_mm']
cover = np.zeros(ct.shape, np.uint8)
BODY_HU = -500
report = []
for z in range(nz):
    fov = fov_per_slice[z]
    disc = rr <= fov / 2 - 0.5 * sx        # acquired region (circular reconstruction field)
    padded = ct[:, :, z] <= -999            # padding or air
    inside = disc & ~padded if fov >= 480 else disc
    cover[:, :, z] = inside
    body = (ct[:, :, z] > BODY_HU) & disc
    # the scanner table is a thin curved shell: an erosion of about 3 mm removes it and keeps limbs
    body = ndimage.binary_erosion(body, iterations=3)
    if body.any():
        lab, n = ndimage.label(body)
        sizes = np.bincount(lab.ravel())[1:]
        # keep components of at least 2 cm^2 after erosion (trunk, limbs); drop table remnants and noise
        body = np.isin(lab, np.where(sizes * sx * sy >= 200)[0] + 1)
        body = ndimage.binary_dilation(body, iterations=3) & disc
    ring = disc & ~ndimage.binary_erosion(disc, iterations=2)
    touch = int((body & ring).sum())
    edge_x = int((body[:3, :].sum() + body[-3:, :].sum()))
    report.append({'z': z, 'fov_mm': float(fov), 'body_voxels': int(body.sum()), 'body_on_fov_edge_voxels': touch, 'body_on_image_edge_voxels': edge_x})
nib.save(nib.Nifti1Image(cover, img.affine), D / 'ct-coverage-mask.nii.gz')
trunc = [r for r in report if r['body_on_fov_edge_voxels'] > 0]
def runs(zs):
    out = []
    for z in zs:
        if out and z == out[-1][1] + 1: out[-1][1] = z
        else: out.append([z, z])
    return out
summary = {
    'ct_file': meta['file'], 'ct_sha256': meta['sha256'], 'body_threshold_hu': BODY_HU,
    'fov_mm_by_slice_range': [{'z_first': s['first_index'], 'z_last': s['last_index'], 'fov_mm': s['fov_mm'], 'exam': s['exam']} for s in meta['segments']],
    'slices_with_body_on_fov_edge': len(trunc), 'z_ranges_with_truncation': runs([r['z'] for r in trunc]),
    'truncated_voxels_total': int(sum(r['body_on_fov_edge_voxels'] for r in trunc)),
    'rule': 'voxels with coverage 0 are unknown for every CT-derived prior; photograph-derived structures are never clipped against the CT there',
    'per_slice': report,
}
(ROOT / 'generated/nlm-ct-coverage.json').write_text(json.dumps(summary, indent=1) + '\n')
print('slices with body touching the field-of-view edge:', len(trunc))
print('z ranges:', summary['z_ranges_with_truncation'])
