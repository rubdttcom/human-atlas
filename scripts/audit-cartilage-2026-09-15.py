#!/usr/bin/env python
"""Reproduce sections 3 to 5 of docs/findings-2026-09-15-ct-prior-score-and-cartilage.md.

Reads only artefacts already in the repository and prints the figures the document
quotes. It changes nothing, writes nothing and grades nothing: the acceptance
status of both variants comes from scripts/cryo-pilot-evaluate.py, not from here.
"""
import numpy as np
import nibabel as nib
from scipy import ndimage as ndi

K0 = 2285                      # first k of block 2
BAND1 = (2528, 2677)           # carries reference cartilage
BAND2 = (2870, 3019)           # carries none
BONE, CART, MUSCLE, IGNORE = 1, 2, 3, 255
TISSUE = {0: "background", 1: "bone", 2: "cartilage", 3: "muscle", 255: "ignore (unlabelled)"}
BLOCK = "data/derived/nlm-vhf/cryosections/block2"
PREDS = (("rgb-only", "data/derived/nnunet/pred/pred-block2-rgb-only.nii.gz"),
         ("rgb+ct-prior", "data/derived/nnunet/pred/pred-block2-rgb-plus-ct-prior.nii.gz"))


def band(k0k1):
    return slice(k0k1[0] - K0, k0k1[1] - K0 + 1)


def main():
    ref_img = nib.load(BLOCK + "/tissue-classes.nii.gz")
    ref = np.asarray(ref_img.dataobj)
    sp = float(ref_img.header.get_zooms()[0])
    den = np.asarray(nib.load(BLOCK + "/denver-original-labels.nii.gz").dataobj)
    print("reference %s, in-plane spacing %.3f mm" % (ref.shape, sp))

    # --- section 5: thickness of the reference cartilage -------------------
    c = ref[:, :, band(BAND1)] == CART
    per_slice = []
    for z in range(c.shape[2]):
        if c[:, :, z].any():
            per_slice.append(2.0 * ndi.distance_transform_edt(c[:, :, z], sampling=(sp, sp)).max())
    per_slice = np.array(per_slice)
    lamina = 2 * ndi.distance_transform_edt(c, sampling=(sp, sp, 1.0))[c].mean()
    print("\n[5] reference cartilage, band 1")
    print("    slices carrying cartilage: %d" % len(per_slice))
    print("    mean lamina thickness: %.2f mm (%.1f px)" % (lamina, lamina / sp))
    print("    per-slice max thickness: median %.2f mm, p05 %.2f, p95 %.2f" % (
        np.median(per_slice), np.percentile(per_slice, 5), np.percentile(per_slice, 95)))

    # --- sections 3 and 4: what the models predict in band 2 ---------------
    b2 = band(BAND2)
    ref2, den2 = ref[:, :, b2], den[:, :, b2]
    bone_d = ndi.distance_transform_edt(ref2 != BONE, sampling=(sp, sp, 1.0))
    centre = ref2.shape[1] / 2.0
    print("\n[3,4] band 2 (k %d..%d), reference cartilage voxels: %d"
          % (BAND2[0], BAND2[1], int((ref2 == CART).sum())))
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
        print("     distance to nearest reference bone: median %.2f mm, p90 %.2f, max %.2f"
              % (np.median(d), np.percentile(d, 90), d.max()))
        print("     lateral offset from midline: median %.1f px (%.1f mm)"
              % (np.median(np.abs(np.where(fp)[1] - centre)),
                 sp * np.median(np.abs(np.where(fp)[1] - centre))))
        _, n_comp = ndi.label(fp)
        print("     connected components: %d" % n_comp)
        on_bone = fp & (ref2 == BONE)
        if on_bone.any():
            dv, dc = np.unique(den2[on_bone], return_counts=True)
            print("     Denver structures under the voxels on labelled bone:")
            for v, cnt in sorted(zip(dv.tolist(), dc.tolist()), key=lambda t: -t[1])[:5]:
                print("        label %-5s %6d voxels" % (v, cnt))


if __name__ == "__main__":
    main()
