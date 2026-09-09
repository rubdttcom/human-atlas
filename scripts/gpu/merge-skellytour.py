"""Stitch Skellytour chunk outputs (postprocessed preferred) back onto the full CT grid. Usage: merge-skellytour.py <ct.nii.gz> <outdir>"""
import sys, json, glob, nibabel as nib, numpy as np
inp, out = sys.argv[1], sys.argv[2]
im = nib.load(inp); plan = json.load(open(f"{out}/chunks/plan.json")); i0, i1, j0, j1 = plan['crop']
full = np.zeros(im.shape, np.uint8); done = []
for p in plan['chunks']:
    c = p['chunk']
    cands = sorted(glob.glob(f"{out}/chunks/out{c}/*_postprocessed.nii.gz")) or sorted(f for f in glob.glob(f"{out}/chunks/out{c}/*.nii.gz") if 'temp' not in f)
    if not cands: print('missing chunk', c); continue
    seg = np.asanyarray(nib.load(cands[0]).dataobj).astype(np.uint8)
    a, b = p['core0'] - p['z0'], p['core1'] - p['z0']
    full[i0:i1, j0:j1, p['core0']:p['core1']] = seg[:, :, a:b]; done.append(c)
    print('chunk', c, cands[0].split('/')[-1], 'labels', int(len(np.unique(seg)) - 1))
nib.save(nib.Nifti1Image(full, im.affine), f"{out}/skellytour_high.nii.gz")
u, n = np.unique(full, return_counts=True)
json.dump({'source': inp, 'chunks_done': done, 'labels': int(len(u) - 1), 'label_voxels': {int(k): int(v) for k, v in zip(u[1:], n[1:])}}, open(f"{out}/skellytour_high.json", 'w'), indent=1)
print('merged labels', len(u) - 1, 'voxels', int(n[1:].sum()), 'chunks', done, 'of', len(plan['chunks']))
