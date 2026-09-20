#!/usr/bin/env python
"""Reproduce sections 3 to 5 of docs/findings-2026-09-15-ct-prior-score-and-cartilage.md.

Reads only artefacts already in the repository and prints the figures the document
quotes. It changes nothing, writes nothing and grades nothing: the acceptance
status of both variants comes from scripts/cryo-pilot-evaluate.py, not from here.

Corrected on 2026-09-20 after the external audit of a446ca8 (section 10 of the
document). The first version (a) used 1 mm between slices instead of the header's
0.333 mm in every 3D distance, (b) measured "lateral offset" along axis j, which is
anterior-posterior in this RAS volume, from the image centre and over all predicted
cartilage, and (c) called 2 x mean(interior EDT) a lamina thickness. This version
takes every spacing from the header, measures the left-right offset along axis i
from the sacral midline and only over voxels on the sacrum, reports the distance to
the nearest non-sacral bone (the sacroiliac test), and estimates thickness as
2 x EDT on the skeleton (local thickness). The old estimator is still printed,
labelled, so the corrected numbers can be checked against the published ones.
"""
import numpy as np
import nibabel as nib
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

K0 = 2285                      # first k of block 2
BAND1 = (2528, 2677)           # carries reference cartilage
BAND2 = (2870, 3019)           # carries none
BONE, CART, MUSCLE, IGNORE = 1, 2, 3, 255
TISSUE = {0: "background", 1: "bone", 2: "cartilage", 3: "muscle", 255: "ignore (unlabelled)"}
SACRUM = (78, 13)              # Denver Right_Bone_Sacrum, Left_Bone_Sacrum
BLOCK = "data/derived/nlm-vhf/cryosections/block2"
PREDS = (("rgb-only", "data/derived/nnunet/pred/pred-block2-rgb-only.nii.gz"),
         ("rgb+ct-prior", "data/derived/nnunet/pred/pred-block2-rgb-plus-ct-prior.nii.gz"))


def band(k0k1):
    return slice(k0k1[0] - K0, k0k1[1] - K0 + 1)


def pct(a, q):
    return np.percentile(a, q)


def main():
    ref_img = nib.load(BLOCK + "/tissue-classes.nii.gz")
    ref = np.asarray(ref_img.dataobj)
    sx, sy, sz = (float(v) for v in ref_img.header.get_zooms())
    axes = nib.aff2axcodes(ref_img.affine)
    den = np.asarray(nib.load(BLOCK + "/denver-original-labels.nii.gz").dataobj)
    print("reference %s, spacing %.3f x %.3f x %.3f mm, axes %s (i = left-right, j = anterior-posterior)"
          % (ref.shape, sx, sy, sz, "".join(axes)))
    assert axes == ("R", "A", "S"), axes

    # --- section 5: thickness of the reference cartilage -------------------
    c = ref[:, :, band(BAND1)] == CART
    edt = ndi.distance_transform_edt(c, sampling=(sx, sy, sz))
    per_slice = []
    for z in range(c.shape[2]):
        if c[:, :, z].any():
            per_slice.append(2.0 * ndi.distance_transform_edt(c[:, :, z], sampling=(sx, sy)).max())
    per_slice = np.array(per_slice)
    skel = skeletonize(c)
    local = 2.0 * edt[skel]
    old_wrong = 2 * ndi.distance_transform_edt(c, sampling=(sx, sy, 1.0))[c].mean()
    old_right = 2 * edt[c].mean()
    print("\n[5] reference cartilage, band 1")
    print("    slices carrying cartilage: %d" % len(per_slice))
    print("    local thickness, 2 x EDT on the 3D skeleton (%d voxels): median %.2f mm (%.1f px), "
          "mean %.2f, p05 %.2f, p95 %.2f" % (skel.sum(), np.median(local), np.median(local) / sx,
                                             local.mean(), pct(local, 5), pct(local, 95)))
    print("    per-slice max local thickness: median %.2f mm, p05 %.2f, p95 %.2f"
          % (np.median(per_slice), pct(per_slice, 5), pct(per_slice, 95)))
    print("    superseded estimator 2 x mean interior EDT: %.2f mm with the real spacing; "
          "%.2f mm as first published (1 mm slice spacing)" % (old_right, old_wrong))

    # --- sections 3 and 4: what the models predict in band 2 ---------------
    b2 = band(BAND2)
    ref2, den2 = ref[:, :, b2], den[:, :, b2]
    bone_d = ndi.distance_transform_edt(ref2 != BONE, sampling=(sx, sy, sz))
    sac = np.isin(den2, SACRUM)
    other_bone = (ref2 == BONE) & ~sac
    other_d = ndi.distance_transform_edt(~other_bone, sampling=(sx, sy, sz))
    si, sj, sk = np.where(sac)
    mid_i, mid_j = si.mean(), sj.mean()
    print("\n[3,4] band 2 (k %d..%d), reference cartilage voxels: %d"
          % (BAND2[0], BAND2[1], int((ref2 == CART).sum())))
    print("    sacrum (Denver 78 + 13): centroid i %.1f (image centre %.1f), j %.1f; both Denver halves "
          "span i %d..%d, so the label split is not left-right" % (mid_i, ref2.shape[0] / 2.0, mid_j,
                                                                  si.min(), si.max()))
    for name, path in PREDS:
        fp = np.asarray(nib.load(path).dataobj)[:, :, b2] == CART
        n = int(fp.sum())
        print("\n  %s: %d cartilage voxels predicted" % (name, n))
        if not n:
            continue
        vals, counts = np.unique(ref2[fp], return_counts=True)
        for v, cnt in sorted(zip(vals.tolist(), counts.tolist()), key=lambda t: -t[1]):
            print("     on %-22s %8d (%5.1f%%)" % (TISSUE.get(v, v), cnt, 100.0 * cnt / n))
        d = bone_d[fp]
        print("     distance to nearest reference bone: median %.2f mm, p90 %.2f, max %.2f; "
              "%.1f%% at distance 0 (inside the bone label, not on its surface)"
              % (np.median(d), pct(d, 90), d.max(), 100.0 * (d == 0).mean()))
        _, n_comp = ndi.label(fp)
        print("     connected components: %d" % n_comp)
        on_sac = fp & sac
        if not on_sac.any():
            continue
        dv, dc = np.unique(den2[fp & (ref2 == BONE)], return_counts=True)
        print("     Denver structures under the voxels on labelled bone:")
        for v, cnt in sorted(zip(dv.tolist(), dc.tolist()), key=lambda t: -t[1])[:5]:
            print("        label %-5s %6d voxels" % (v, cnt))
        i, j, k = np.where(on_sac)
        lat = np.abs(i - mid_i) * sx
        ap = (j - mid_j) * sy
        print("     on the sacrum: %d voxels on %d slices (k %d..%d)"
              % (on_sac.sum(), len(np.unique(k)), k.min() + BAND2[0], k.max() + BAND2[0]))
        print("       left-right offset from the sacral midline (axis i): median %.1f mm, p10 %.1f, p90 %.1f"
              % (np.median(lat), pct(lat, 10), pct(lat, 90)))
        print("       anterior-posterior offset from the sacral centroid (axis j): median %+.1f mm"
              % np.median(ap))
        do = other_d[on_sac]
        print("       distance to the nearest non-sacral reference bone: median %.1f mm, p10 %.1f"
              % (np.median(do), pct(do, 10)))
        print("       superseded figure (axis j, image centre, all predicted cartilage): %.1f mm"
              % (sy * np.median(np.abs(np.where(fp)[1] - ref2.shape[1] / 2.0))))


if __name__ == "__main__":
    main()
