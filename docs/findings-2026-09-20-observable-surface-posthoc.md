# The surface error measured on observable boundaries: a post hoc analysis

Written on 2026-09-20, after both pilot variants were scored under acceptance protocol v1
(`generated/cryo-pilot-acceptance-block2-rgb-only.json`, 2026-09-14;
`generated/cryo-pilot-acceptance-block2-rgb-plus-ct-prior.json`, 2026-09-15). **Nothing here is an
acceptance result.** The v1 scores stand on the record, both variants stay `machine-failed` on all
three classes, and no threshold, evaluator or status is changed. This document does what the audit of
a446ca8 asked for: it designs an evaluation of observable surfaces, labels it post hoc, and reports what
it says about the two predictions that already exist.

## 1. Why this is post hoc, and what that costs

The argument that the v1 surface p95 does not measure a boundary was filed before any new number
existed (`docs/findings-2026-09-14-rgb-only-first-score.md`, section 1, and `docs/PROGRESS.md`,
"This closes the pre-score window for protocol v2"). The metric below was still designed knowing the
v1 scores and the direction of the artefact. That is the definition of post hoc. Consequences:

- it cannot accept or fail these two variants; a number that clears a threshold here is not a pass;
- it can only be a candidate criterion for a protocol v2, to be frozen before any variant trained
  after 2026-09-20 is scored;
- its own controls are reported so the auditor can judge whether it discriminates where v1 did not.

## 2. The metric (`scripts/cryo_posthoc_surface.py`)

Protocol v1 (`scripts/cryo_metrics.py`) removes from both surfaces every voxel whose 6-neighbourhood
touches an `ignore` voxel, then measures from the remainder of each surface to the remainder of the
other. On Denver's labels, which leave the tissue around each structure unlabelled, that removes
79 % of the reference bone surface and 52 % of the prediction surface (band 2, `rgb-only`). The
prediction boundaries that survive are the ones inside the reference structure (an under-segmented
rim), and their nearest surviving reference voxel is tens of millimetres away.

The post hoc metric keeps v1's eligibility, runs, emptiness statuses, spacing and tolerance, and
changes two things:

1. **Source sets are observable boundaries.** A surface voxel of a mask is a source only when it is
   eligible and at least one of its outside 6-neighbours is eligible: the reference labels both sides
   of that boundary, so it can say whether the boundary belongs there. A boundary against `ignore`
   is never a source. Surfaces are computed on the unrestricted masks, so the ignore region creates
   no pseudo-boundary. The six faces of the run volume are removed as in v1.
2. **Target sets are full boundaries.** Observable prediction boundaries are measured to the full
   reference surface; observable reference boundaries to the full prediction surface. Denver labels a
   structure completely, so every voxel of its boundary is an observed boundary of that class even
   where the class of the voxel outside is unknown. A larger target can only shorten a distance.

Support is reported per mask: surface voxels, observable, and against ignore. The last figure is
the metric's blind spot: over- or under-extension of a class into unlabelled tissue is counted,
never measured.

`scripts/test-cryo-posthoc-surface.py` (8 cases) reproduces the v1 artefact on a toy: a structure
surrounded by ignore with a 3 px missed rim scores p95 11.40 mm under v1 and 2.00 mm post hoc; on a
fully labelled block both metrics agree (1 px erosion 0.666 mm, 3 px shift 1.998 mm, identity 0);
a 5 px extension into ignore scores 0 and is counted; faces, empty prediction and false-positive-only
runs behave as in v1.

## 3. Results on the two existing predictions

Report: `generated/cryo-posthoc-observable-surface-block2.json` (780 s; bound by hash to both predictions,
both v1 acceptance reports, the reference volume, the bands and the metric file). Same eligible slices,
runs and perturbations as v1. Evaluator sanity on the reference under the post hoc metric: mirror 9.66 /
15.94 / 8.43 mm, +3 px shift 1.998 mm, 3 px dilation 1.998 mm for bone / cartilage / muscle, every one
degrading from 0 by more than the 0.333 mm tolerance.

### 3.1 Bone: the boundary error is 3 to 8 mm, not 30

| variant | v1 p95 | post hoc p95 | post hoc p50 | prediction -> reference p95 | reference -> prediction p95 |
|---|---|---|---|---|---|
| rgb-only | 32.27 mm | **7.71 mm** | 0.94 mm | 8.66 mm | 3.14 mm |
| rgb-plus-ct-prior | 27.21 mm | **3.41 mm** | 0.67 mm | 5.04 mm | 2.00 mm |

Support: 222,853 / 160,315 observable prediction boundary voxels (of 1.34 M / 0.92 M), 83,256 observable
reference boundary voxels of 578,905; 495,649 reference bone boundary voxels face `ignore` and serve only
as targets. Per band: rgb-only 4.42 / 8.45 mm, rgb-plus-ct-prior 2.75 / 4.74 mm (band 1 / band 2).

The metric discriminates here. Model-side controls under the post hoc metric: rgb-only shift 8.27,
dilation 10.04, mirror 24.73 mm; rgb-plus-ct-prior shift 3.90, dilation 4.32, mirror 16.89 mm; every one
degrades the base p95 by more than the tolerance, where under v1 the same perturbations could not move a
p95 dominated by 30 mm. Wrong-neighbour baseline on the same slices: p95 7.12 mm, p50 2.23 mm.
rgb-plus-ct-prior beats it on p95 (3.88 mm); rgb-only does not on p95 (8.11 mm) and does on p50
(0.94 mm). The far tail is small and real: 1.9 to 3.4 % of the observable prediction boundaries lie more
than 10 mm from any reference bone boundary, almost all of them under reference bone with predicted muscle
across: deep interior misses (`scripts/audit-posthoc-far-boundaries.py bone`).

Both variants remain far above the v1 threshold of 0.9419 mm, which was set from the Denver
inter-annotator surface floor. Had this metric been the protocol, both would still fail bone on p95.

### 3.2 Muscle: the number is still not a muscle boundary error

| variant | v1 p95 | post hoc p95 | post hoc p50 | prediction -> reference p95 | reference -> prediction p95 |
|---|---|---|---|---|---|
| rgb-only | 35.81 mm | 30.53 mm | 1.33 mm | 32.69 mm | 3.33 mm |
| rgb-plus-ct-prior | 31.20 mm | 25.97 mm | 0.67 mm | 33.93 mm | 1.79 mm |

The reference -> prediction direction is 2 to 3 mm: every labelled muscle boundary has a predicted
boundary close to it. The prediction -> reference direction is 33 mm, the shift control does not degrade
either variant (30.75 and 23.82 mm), and neither beats the wrong neighbour (4.81 mm). Diagnosis
(`scripts/audit-posthoc-far-boundaries.py muscle`): in band 2, 40.6 % (rgb-only) and 20.3 %
(rgb-plus-ct-prior) of the observable muscle prediction boundaries lie more than 10 mm from any reference
muscle boundary. They sit under **reference bone**, with **predicted bone** across the boundary: they are
the under-segmented bone rim of section 3.1, counted a second time as a muscle boundary, and measured
against a muscle reference that contains only the 76 muscles Denver modelled. In the pelvis most muscle is
`ignore`, so the nearest labelled muscle boundary can be centimetres away from a rim that is 2 mm wrong.

This is a limit of the post hoc metric, found on the data: assumption 2 of section 2 (the reference
surface of a class is fully observed) holds for bone, which Denver labels completely in this region, and
fails for muscle. A boundary error should be attributed to the class the REFERENCE has there, once. The
candidate rule for v2 is stated in section 4 and is **not** applied here, because applying a second
post hoc refinement to the same two predictions is the metric-tuning this document exists to avoid.

### 3.3 Cartilage: the metric cannot discriminate at this error level

| variant | v1 p95 | post hoc p95 | post hoc p50 | prediction -> reference p95 | reference -> prediction p95 |
|---|---|---|---|---|---|
| rgb-only | 36.76 mm | 36.64 mm | 1.33 mm | 51.02 mm | 14.88 mm |
| rgb-plus-ct-prior | 11.80 mm | 13.81 mm | 1.00 mm | 9.26 mm | 15.36 mm |

Cartilage barely touches `ignore` (510 / 321 prediction boundary voxels against ignore), so v1 and the
post hoc metric see almost the same surfaces and agree. For rgb-plus-ct-prior none of the three
model-side perturbations degrades the p95 (mirror 11.86, shift 13.94, dilation 13.61 against 13.81 mm):
a 2 mm perturbation is invisible under a 14 mm error, so the surface metric says nothing more about this
class than "wrong by more than a centimetre at the 95th percentile". Both variants lose to the wrong
neighbour (7.80 mm). Band 2 is `false-positives-only` (7,581 / 5,524 voxels on labelled tissue) and is
left out of the surface pool exactly as in v1; the midline sacral voxels of the previous findings
document are among them.

## 4. What follows

- **Protocol v2 candidate.** The observable-boundary p95 of section 2 with one more rule, from
  section 3.2: a source boundary voxel of class X counts only where the reference assigns X to that
  voxel or to the eligible voxel across the boundary, so that an error is attributed to the class the
  reference has there and only once. Plus the two terms the audit of a446ca8 asked for: predicted
  volume of each class on `ignore` reported per band (never scored), and median distance from
  predicted cartilage to the nearest predicted bone (a required neighbour; blind to the ignore mask).
  Thresholds stay the v1 Denver floors unless a new floor is measured with the same metric on the
  Denver inter-annotator data. To be written, tested on synthetic cases and hash-pinned before the
  next variant is trained, with the Codex auditor checking the diff against v1. Not applied to the
  two existing predictions.
- **What the analysis says about the CT prior**, for what post hoc evidence is worth: on bone, the
  only class where the metric measures what it names, the prior halves the observable boundary
  error (7.71 -> 3.41 mm p95, 0.94 -> 0.67 mm p50) and turns the wrong-neighbour comparison from
  lost to won. It agrees with the v1 Dice direction and adds nothing to acceptance.
- **These two variants keep their v1 status.** Their post hoc figures are evidence about the
  metric, not about acceptance.
- **Cartilage.** The midline sacral voxels of the findings of 2026-09-15 section 4 remain
  unexplained until someone looks at k 2892..2979. Nothing here touches that.

## 5. Reproducing

```
.venv/bin/python scripts/test-cryo-posthoc-surface.py
.venv/bin/python scripts/cryo-posthoc-observable-surface.py --block data/derived/nlm-vhf/cryosections/block2 \
    --variant rgb-only=data/derived/nnunet/pred/pred-block2-rgb-only.nii.gz \
    --variant rgb-plus-ct-prior=data/derived/nnunet/pred/pred-block2-rgb-plus-ct-prior.nii.gz
.venv/bin/python scripts/audit-posthoc-far-boundaries.py muscle
```

## 6. What is not claimed

No anatomy. No validation. No change to any frozen file. The v1 results are quoted, not replaced.
A prediction boundary against unlabelled tissue is invisible to every distance here, so a model that
paints a class across `ignore` at any scale still scores by what it does on labelled tissue only.
