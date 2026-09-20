# The CT prior scored, and what the cartilage class is actually doing

Prepared for external audit on 2026-09-15. Variant `rgb-plus-ct-prior` (Dataset502) finished its
1000 epochs at 02:19 and now has a score under acceptance protocol v1, against the same frozen bands
as `rgb-only`. This document compares the two, and reports three measurements about the cartilage
class that the acceptance reports do not contain.

Reports read: `generated/cryo-pilot-acceptance-block2-rgb-only.json` (2026-09-14) and
`generated/cryo-pilot-acceptance-block2-rgb-plus-ct-prior.json` (2026-09-15). Both have
`evaluator_trusted: true`. The earlier findings document
`docs/findings-2026-09-14-rgb-only-first-score.md` is assumed read; its section 1 (the caps artefact
in the surface metric) explains every p95 figure below and is not repeated.

## 1. Both variants side by side

| Class | threshold | rgb-only Dice | rgb+ct-prior Dice | rgb-only p95 | rgb+ct-prior p95 |
|---|---|---|---|---|---|
| bone | Dice >= 0.9324, p95 <= 0.9419 mm | 0.9290 | **0.9699** | 32.27 mm | 27.21 mm |
| muscle | Dice >= 0.9105, p95 <= 0.9419 mm | 0.9718 | **0.9891** | 35.81 mm | 31.20 mm |
| cartilage | p95 <= 0.9704 mm (Dice reported only) | 0.2973 | **0.4285** | 36.76 mm | **11.80 mm** |

**Both variants remain `machine-failed` on all three classes.** No threshold is revised here.

The change that matters: `rgb-only` missed the bone Dice floor by 0.0034 (0.9290 against 0.9324).
`rgb-plus-ct-prior` clears it by 0.0375 (0.9699). The bone `reason` string loses its
`dice below 0.9324` clause and keeps only the p95 clause and the two controls that the caps artefact
disables. On the one criterion that section 1 of the previous findings did not explain away, the CT
prior turns a failure into a pass.

Cartilage p95 falls from 36.76 mm to 11.80 mm. Both still fail the 0.9704 mm bar.

## 2. Model-side controls

| Class | control | rgb-only | rgb+ct-prior | model rgb-only | model rgb+ct-prior |
|---|---|---|---|---|---|
| cartilage | dilation | 0.3276 | 0.3951 | 0.2973 | 0.4285 |
| cartilage | shift | 0.2963 | 0.3862 | 0.2973 | 0.4285 |
| cartilage | wrong neighbour 10 mm | 0.3950 | 0.3950 | 0.2405 | 0.3310 |
| bone | wrong neighbour 10 mm | 0.7804 | 0.7804 | 0.9321 | 0.9716 |
| muscle | wrong neighbour 10 mm | 0.8540 | 0.8540 | 0.9712 | 0.9887 |

Two readings, both worth auditing:

- `rgb-only` cartilage scores **below its own dilated copy** (0.2973 against 0.3276) and level with
  its own shifted copy. `rgb-plus-ct-prior` beats both. That is a change in kind, not degree.
- **Cartilage still loses to the wrong-neighbour baseline in both variants** (0.3310 against 0.3950).
  Labels copied from a centimetre away still beat the model. By the reading of the previous findings
  document, the class has not learned position. The gap narrows from 0.1545 to 0.0640.

## 3. The protocol does not see 98.5 % of the rgb-only cartilage volume

Band 2 (k 2870..3019) has no reference cartilage. The acceptance reports record 7,581 false-positive
cartilage voxels for `rgb-only` and 5,524 for `rgb-plus-ct-prior`, and both are kept out of the
surface pool as `false-positives-only`. Those counts are correct, and they are a small fraction of
what the models actually predict there.

Counting every cartilage voxel predicted in the band, not only those landing on labelled reference:

| | predicted cartilage in band 2 | on labelled bone | on `ignore` (unlabelled tissue) |
|---|---|---|---|
| rgb-only | **491,401** | 7,576 (1.5 %) | **483,820 (98.5 %)** |
| rgb+ct-prior | 10,318 | 5,524 (53.5 %) | 4,794 (46.5 %) |

`rgb-only` paints 491,401 cartilage voxels into a band where Denver labels none. All but 1.5 % of
them land on tissue Denver never labelled, so they are `ignore`, so the evaluator is silent about
them. The reported 7,581 is the evaluable 1.5 % of a predicted volume 65 times larger.

**What the 483,820 voxels are, and are not** (wording corrected 2026-09-20, section 10). They are
predictions with no evaluable reference. They are not demonstrated errors: Denver labelled only the
structures it modelled, so some unlabelled tissue may be cartilage Denver omitted. The evidence that
most of them are wrong is indirect and comes from the distance table below, not from the count. A
protocol v2 term that penalised volume on `ignore` as such would also penalise structures Denver
omitted, so it cannot be a plain error term; a distance-to-required-neighbour term does not have that
problem.

This is not a defect in the evaluator: scoring against unobserved reference is exactly what the
ignore rule exists to prevent, and the previous findings document defends that rule. It is a
**blind spot in the acceptance criteria**, which contain no term for the total volume a class
predicts. A model can paint a class across unlabelled tissue at any scale and the protocol will
not record it.

Distance from each predicted cartilage voxel to the nearest reference bone, same band, all three
spacings from the header (0.666 x 0.666 x 0.333 mm; the first publication used 1 mm between slices,
section 10):

| | median | p90 | max | share at distance 0 |
|---|---|---|---|---|
| rgb-only | **49.65 mm** | 98.40 mm | 144.49 mm | 1.5 % |
| rgb+ct-prior | **0.00 mm** | 13.75 mm | 41.20 mm | 53.5 % |

Articular cartilage exists only on a bone surface. `rgb-only` puts half its cartilage about 50 mm
from any labelled bone, which no anatomy supports. For `rgb-plus-ct-prior` the median voxel is at
distance 0, which means **inside Denver's bone label**, not on its surface: the two readings are
"the model paints cartilage over bone Denver calls bone" or "Denver's bone label covers a surface
layer that is cartilage". The distance alone does not separate them. Connected components in the
band: 2,117 for `rgb-only`, 32 for `rgb-plus-ct-prior`.

Suggested as a protocol v2 criterion, not adopted here: median distance from each predicted voxel
of a class to the nearest anatomically required neighbour class, computed over the whole band and
so blind to the ignore mask. Predicted volume on `ignore` should be reported alongside it, not
scored. Both are computable from artefacts that already exist and neither touches a frozen
threshold.

## 4. The rgb+ct-prior cartilage false positives sit on the sacrum, near its midline

Denver structures beneath the cartilage voxels that land on labelled bone in band 2:

| Denver label | structure | rgb-only | rgb+ct-prior |
|---|---|---|---|
| 78 | Right_Bone_Sacrum | 4,608 | 4,264 |
| 13 | Left_Bone_Sacrum | 2,777 | 1,260 |
| 11 | Left_Bone_Pelvis | 191 | 0 |

Both variants put this part of their cartilage on the sacrum. The first publication read the two
Denver names as "both sides" and quoted a median "lateral offset from the midline" of 85 px =
56.6 mm. Both statements were wrong and are withdrawn (section 10): the offset was measured along
axis j, which is anterior-posterior in this RAS volume, from the image centre, over all predicted
cartilage; and in band 2 both Denver sacrum labels span the same left-right range (i 239..421), so
the 78/13 split is not a left-right split and the names say nothing about bilaterality.

Measured correctly, over the voxels on the sacrum only, left-right along axis i from the sacral
centroid (i 329.8; the image centre is 333.0):

| | on sacrum | slices | left-right offset median (p10, p90) | AP offset from sacral centroid | distance to nearest non-sacral bone median (p10) |
|---|---|---|---|---|---|
| rgb-only | 7,385 | 112 | 8.8 mm (2.2, 20.1) | +8.7 mm (anterior) | 41.8 mm (31.4) |
| rgb+ct-prior | 5,524 | 55 | 7.2 mm (1.2, 30.8) | +3.4 mm (anterior) | 42.9 mm (20.1) |

**The sacroiliac hypothesis of the first publication is not supported by this measurement.**
Sacroiliac cartilage lies where the sacrum meets the ilium, so voxels on it would be within a few
millimetres of the pelvis label. The predicted voxels sit a median 7 to 9 mm from the sacral midline
and about 42 mm from any non-sacral bone, slightly anterior of the sacral centroid, in a few groups
of slices. That is a midline, anterior sacral location, not a joint surface facing the ilium.

**Hypothesis, not a measurement, and weaker than the last one.** A midline anterior structure on
the upper sacrum that looks like cartilage in a photograph could be an intervertebral disc or its
endplates (the lumbosacral transition of this donor is an open question,
`docs/plans/vhf-s1-lumbosacral-dossier.md`), a sacral fusion remnant, or plain confusion of the
class at a bone boundary. Denver labels none of these as cartilage. Nothing here decides between
them. **Nobody has looked at the photographs.** The check is the same as before: open the slices
k 2892..2979 at the sacral midline and see what tissue the voxels cover. Until then these 5,524
voxels stay false positives under the protocol and nothing else.

If unlabelled cartilage turns out to exist in these photographs, the same question applies to the
pubic symphysis and the acetabular labrum, neither of which Denver labels either.

## 5. The reference cartilage is about 2.8 pixels thick

Measured on the 83 band-1 slices that carry reference cartilage, spacing 0.666 x 0.666 x 0.333 mm.
The first publication quoted a "mean lamina thickness" of 1.76 mm from 2 x mean(interior EDT) with
1 mm between slices; that estimator is not a thickness (it averages the depth of every interior
voxel, which for a lamina is about half the thickness) and the spacing was wrong (with the real
spacing it gives 1.58 mm). Both are withdrawn (section 10). Local thickness, 2 x EDT sampled on the
3D skeleton of the label (1,520 skeleton voxels), replaces it:

- local thickness **median 1.88 mm = 2.8 px**, mean 1.83 mm, p05 1.33 mm, p95 2.98 mm;
- per-slice maximum local thickness: median 4.00 mm, p05 2.98 mm, p95 4.74 mm (in-plane only, unchanged).

Published hip cartilage thickness: acetabulum 0.95–3.13 mm and femoral head 0.32–2.53 mm by CT
arthrography ([Radiology 2007](https://pubmed.ncbi.nlm.nih.gov/17255415/)); 1.15–1.46 mm acetabular
and 1.18–1.78 mm femoral by MRI stereology
([Osteoarthritis and Cartilage 2007](https://www.sciencedirect.com/science/article/pii/S1063458406002925)).
Denver's cartilage labels in this block fall inside the published range. That is a plausibility
check on a summary statistic. It does not make the labels anatomically correct, and the first
publication's sentence to that effect is withdrawn: a label can have the right thickness in the
wrong place.

The consequence is for the metric, not the label. A structure under 3 px thick cannot survive a
boundary error of one pixel with a good Dice: a one-pixel offset on a 3 px lamina caps Dice near
0.67. This is why protocol v1 sets no Dice threshold for cartilage and grades it on surface p95
only. **The Dice figures in section 1 are reported, not criteria**, and an auditor should not read
0.4285 as "43 % of the cartilage is right".

Band-1 slice coverage, which is closer to a fair statement of the class: reference carries cartilage
on 83 slices; `rgb-only` predicts it on 116; `rgb-plus-ct-prior` on 81.

## 6. Corrections to statements made earlier in this session

Recorded because they were said aloud before the acceptance reports were read, and an auditor should
know they were wrong:

1. "Cartilage Dice cannot be measured without leakage." **False.** It is measured, on frozen reserved
   bands, with 55,653 reference voxels. The `NaN` that prompted the claim is from nnU-Net's own
   internal fold-0 validation (10 slices, none carrying cartilage), which is not the protocol and
   selects nothing — inference uses `checkpoint_final`.
2. "Bone separates the two variants by 0.002, which is noise." **False.** That was nnU-Net's internal
   pseudo-dice (0.9841 against 0.9860). Under the protocol the gap is 0.9290 against 0.9699, and it
   crosses the acceptance floor.
3. "The 291 predicted slices are unlabelled territory." **False.** They are the two frozen evaluation
   bands and they carry Denver reference.
4. A proposal to reshuffle the fold-0 split so that validation would contain cartilage. **Withdrawn.**
   It targets nnU-Net's internal validation, which grades nothing, and it would have put near-identical
   adjacent slices on both sides of the split.

Section 3 and section 4 stand independent of these errors; they are measured on the reference and the
prediction volumes directly.

## 7. What the audit is asked to check

1. Section 3's counts, from the two prediction volumes and `tissue-classes.nii.gz`. Is the
   ignore-blindness real, and is a predicted-volume term the right answer to it?
2. Section 4, against the photographs: what tissue do the predicted cartilage voxels at the sacral
   midline (k 2892..2979) cover? The sacroiliac reading is withdrawn; the midline reading is a
   hypothesis with no observation behind it.
3. Whether bone clearing its Dice floor under `rgb-plus-ct-prior` changes anything about the
   `machine-failed` status, given that the remaining bone failures are the p95 artefact and the two
   controls that artefact disables. (Audit answer, 2026-09-20: no. Clearing one criterion removes
   neither the surface nor the control failures, and says nothing about generalisation beyond this
   block. The status stands.)
4. The iteration limit. `generated/runs/nnunet-run-provenance-502.json` observes two training logs
   for this variant. The first publication called the first one "a 300-epoch attempt that died";
   that was wrong (section 10). `generated/cryo-nnunet-train-block2-rgb-plus-ct-prior.json` records
   what happened: the user asked for the GPU to be freed, training was stopped after the epoch-300
   checkpoint, and it was continued from `checkpoint_latest.pth` at epoch 300 with the same seed,
   split and data (log 2, epochs 300 to 999). No score existed at the stop. Protocol v1 allows two
   runs per variant. Is one training interrupted by the operator and continued from its own
   checkpoint one run or two? The manifest says one; the auditor should say whether that reading
   holds.
5. The provenance and acceptance artefacts for 502 were written at 07:01 and 07:08 on 2026-09-15 by a
   process this session did not launch. Their contents should be verified rather than trusted.

## 8. Reproducing sections 3 to 5

```
.venv/bin/python scripts/audit-cartilage-2026-09-15.py
```

Volumes used, all already in the repository:

- `data/derived/nlm-vhf/cryosections/block2/tissue-classes.nii.gz` (reference, 0.666 x 0.666 x 0.333 mm,
  RAS: axis i is left-right, axis j anterior-posterior, axis k the slice index)
- `data/derived/nlm-vhf/cryosections/block2/denver-original-labels.nii.gz` (structure identity)
- `data/derived/nnunet/pred/pred-block2-rgb-only.nii.gz`
- `data/derived/nnunet/pred/pred-block2-rgb-plus-ct-prior.nii.gz`

Band 2 is k 2870..3019, band 1 is k 2528..2677, and the block starts at k 2285.

## 9. What is not claimed

Nothing here is anatomy that a person has verified. Section 4 is a hypothesis with a stated test and
no observation behind it. No threshold, metric, evaluator or status is changed by this document. The
`machine-failed` status of both variants stands. Sections 3 to 5 are analyses made after the v1
scores were known; they explain figures, they replace none.

## 10. Corrections after the external audit of a446ca8 (2026-09-20)

The auditor reproduced the counts of section 3, the hashes of both predictions and manifests, ran
the pilot validator and the 25 metric tests, and did not inspect the photographs or the remote
checkpoints. Four findings, all confirmed on the data and applied above; the official Dice and p95
figures of section 1 come from the evaluator and are not affected by any of them.

1. **Slice spacing.** `scripts/audit-cartilage-2026-09-15.py` used 1 mm between slices instead of
   the header's 0.333 mm in every 3D distance. Corrected figures: rgb-only median distance to bone
   55.70 -> 49.65 mm, p90 105.39 -> 98.40, max 154.91 -> 144.49; rgb+ct-prior p90 20.68 -> 13.75,
   max 47.78 -> 41.20; superseded thickness estimator 1.76 -> 1.58 mm. The script now takes all
   three spacings from the header and asserts the RAS orientation.
2. **Wrong axis for "lateral".** The 56.6 mm was measured along axis j (anterior-posterior), from
   the image centre, over all predicted cartilage. Measured along axis i from the sacral centroid
   over the voxels on the sacrum, the offset is a median 7 to 9 mm, and the voxels lie about 42 mm
   from any non-sacral bone. The sacroiliac hypothesis is withdrawn; section 4 now carries a weaker
   midline hypothesis with the same "look at the photographs" test. The Denver 78/13 label names do
   not encode left and right in this band, so "bilaterally" is withdrawn as well.
3. **"A failure 65 times larger".** The 483,820 voxels on `ignore` are predictions without an
   evaluable reference, not demonstrated errors, and distance 0 to the bone label means overlap
   with the label, not position on its surface. Section 3 now says so, and the protocol v2
   suggestion no longer proposes penalising volume on `ignore` as an error term.
4. **Thickness.** 2 x mean(interior EDT) is not a lamina thickness. Replaced by local thickness on
   the 3D skeleton (median 1.88 mm). The sentence declaring Denver's labels "anatomically the right
   thickness" is replaced by a plausibility statement; a thickness in the published range does not
   make a label correct.

Also corrected: item 4 of section 7 called the first log of variant 502 "an attempt that died".
The training manifest records an operator-requested stop at the epoch-300 checkpoint and a
continuation from it; there was no crash and no third attempt. The auditor's recommendation is
adopted as the plan: these results stay on record as evidence in favour of the CT prior under
protocol v1, the auxiliary diagnosis is corrected here, and an evaluation of observable surfaces
is designed as a post hoc analysis, labelled as such, that keeps the v1 results, before the pilot
is extended.
