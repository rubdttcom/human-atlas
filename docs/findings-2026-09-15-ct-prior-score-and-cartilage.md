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

## 3. The protocol does not see 98.5 % of the rgb-only cartilage failure

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
them. The reported 7,581 is the visible 1.5 % of a failure 65 times larger.

This is not a defect in the evaluator: scoring against unobserved reference is exactly what the
ignore rule exists to prevent, and the previous findings document defends that rule. It is a
**blind spot in the acceptance criteria**, which contain no term for the total volume a class
predicts. A model can hallucinate a class across unlabelled tissue at any scale and the protocol
will not record it.

Distance from each predicted cartilage voxel to the nearest reference bone, same band:

| | median | p90 | max |
|---|---|---|---|
| rgb-only | **55.70 mm** | 105.39 mm | 154.91 mm |
| rgb+ct-prior | **0.00 mm** | 20.68 mm | 47.78 mm |

Articular cartilage exists only on a bone surface. `rgb-only` puts half its cartilage more than
55 mm from any bone, which no anatomy supports. `rgb-plus-ct-prior` puts the median voxel **on** the
bone. Connected components in the band: 2,117 for `rgb-only`, 32 for `rgb-plus-ct-prior`.

Suggested as a protocol v2 criterion, not adopted here: predicted volume of a class on ignore
tissue, and median distance to the nearest anatomically required neighbour class. Both are
computable from artefacts that already exist and neither touches a frozen threshold.

## 4. The rgb+ct-prior cartilage false positives sit on the sacrum, bilaterally

Denver structures beneath the cartilage voxels that land on labelled bone in band 2:

| Denver label | structure | rgb-only | rgb+ct-prior |
|---|---|---|---|
| 78 | Right_Bone_Sacrum | 4,608 | 4,264 |
| 13 | Left_Bone_Sacrum | 2,777 | 1,260 |
| 11 | Left_Bone_Pelvis | 191 | 0 |

Both variants put this part of their cartilage on the sacrum, on both sides. Median lateral offset
from the midline is 85 px = 56.6 mm for both.

**Hypothesis, not a measurement.** The sacroiliac joint is at that location, it is bilateral, and it
carries cartilage in life: hyaline on the sacral side, fibrocartilage on the iliac side
([StatPearls, Pelvic Joints](https://www.ncbi.nlm.nih.gov/books/NBK538523/)). The pilot's tissue map
takes cartilage only from Denver, and Denver's cartilage in this block is
"femoral heads and acetabula only" (`generated/cryo-tissue-classes-block2.json`). If real
sacroiliac cartilage is present in these photographs and unlabelled, then some of these false
positives are anatomically right and the reference is incomplete.

This must not be assumed. It predicts something checkable: the voxels should form a thin bilateral
lamina on the sacral surface facing the ilium, not a rim around the whole sacrum. **Nobody has
looked at the photographs.** An anatomist, or the audit, should settle it before it is repeated.

If it holds, the same question applies to the pubic symphysis (fibrocartilage, thicker in females)
and the acetabular labrum, neither of which Denver labels either.

## 5. The reference cartilage is 2.6 pixels thick, and that matches the literature

Measured on the 83 band-1 slices that carry reference cartilage, in-plane spacing 0.666 mm:

- mean lamina thickness **1.76 mm = 2.6 px**;
- per-slice maximum local thickness: median 4.00 mm, p05 2.98 mm, p95 4.74 mm.

Published hip cartilage thickness: acetabulum 0.95–3.13 mm and femoral head 0.32–2.53 mm by CT
arthrography ([Radiology 2007](https://pubmed.ncbi.nlm.nih.gov/17255415/)); 1.15–1.46 mm acetabular
and 1.18–1.78 mm femoral by MRI stereology
([Osteoarthritis and Cartilage 2007](https://www.sciencedirect.com/science/article/pii/S1063458406002925)).
Denver's cartilage labels in this block are anatomically the right thickness. The reference is not
suspect on this count.

The consequence is for the metric, not the label. A structure 2.6 px thick cannot survive a boundary
error of one pixel with a good Dice: a one-pixel offset on a 3 px lamina caps Dice near 0.67. This is
why protocol v1 sets no Dice threshold for cartilage and grades it on surface p95 only. **The Dice
figures in section 1 are reported, not criteria**, and an auditor should not read 0.4285 as "43 % of
the cartilage is right".

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
2. Section 4's hypothesis, against the photographs: is there unlabelled sacroiliac cartilage in
   band 2, or is `rgb-plus-ct-prior` rimming the sacrum?
3. Whether bone clearing its Dice floor under `rgb-plus-ct-prior` changes anything about the
   `machine-failed` status, given that the remaining bone failures are the p95 artefact and the two
   controls that artefact disables.
4. The iteration limit. `generated/runs/nnunet-run-provenance-502.json` records two runs for this
   variant (a 300-epoch attempt that died, and the 1000-epoch resume). Protocol v1 allows two runs
   per variant. Does a crashed run consume one?
5. The provenance and acceptance artefacts for 502 were written at 07:01 and 07:08 on 2026-09-15 by a
   process this session did not launch. Their contents should be verified rather than trusted.

## 8. Reproducing sections 3 to 5

```
.venv/bin/python scripts/audit-cartilage-2026-09-15.py
```

Volumes used, all already in the repository:

- `data/derived/nlm-vhf/cryosections/block2/tissue-classes.nii.gz` (reference, 0.666 x 0.666 x 0.333 mm)
- `data/derived/nlm-vhf/cryosections/block2/denver-original-labels.nii.gz` (structure identity)
- `data/derived/nnunet/pred/pred-block2-rgb-only.nii.gz`
- `data/derived/nnunet/pred/pred-block2-rgb-plus-ct-prior.nii.gz`

Band 2 is k 2870..3019, band 1 is k 2528..2677, and the block starts at k 2285.

## 9. What is not claimed

Nothing here is anatomy that a person has verified. Section 4 is a hypothesis with a stated test and
no observation behind it. No threshold, metric, evaluator or status is changed by this document. The
`machine-failed` status of both variants stands.
