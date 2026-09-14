# First graded result of the RGB pilot, and what the surface metric actually measured

Variant `rgb-only`, nnU-Net v2 2D fold 0, Denver block 2, scored against the frozen bands of
`registry/cryo-eval-bands-v1.json` under acceptance protocol v1 on 2026-09-14.
Report: `generated/cryo-pilot-acceptance-block2-rgb-only.json`. Evaluator self-check passed
(`evaluator_trusted: true`), 512 s.

**All three classes are `machine-failed`.** That status stands and is not revised here. Nothing below
changes a threshold, a metric or the evaluator: those are frozen, and a score now exists.

| Class | Dice | threshold | surface p95 | threshold |
|---|---|---|---|---|
| bone | 0.9290 | 0.9324 | 32.27 mm | 0.9419 mm |
| muscle | 0.9718 | 0.9105 | 35.81 mm | 0.9419 mm |
| cartilage | 0.2973 | none | 36.76 mm | 0.9704 mm |

## 1. The p95 figures do not measure a boundary error

A model with Dice 0.97 cannot have a boundary 35 mm out of place. The cause is in the metric, and it
is measurable.

`scripts/cryo_metrics.py` removes surface voxels whose 6-neighbourhood touches an ineligible voxel
(`_caps`). Ineligible means the reference says `ignore`: unlabelled tissue inside the body. Denver
labels individual structures and leaves everything around them unlabelled, so a Denver structure is
almost entirely *surrounded* by ignore. Measured on the bone of band 2 (k 2870..3019):

- reference surface: 243,322 voxels raw, 51,138 kept. **79.0 % removed as caps.**
- prediction surface: 276,551 voxels raw, 132,739 kept. **52.0 % removed.**

The distances are therefore measured from a nearly complete prediction surface to a 21 % remnant of
the reference surface, and the nearest surviving reference voxel can be tens of millimetres away.
99.8 % of the predicted surface voxels that lie more than 10 mm from the remnant are *inside* the
reference bone.

Recomputing the same distances against the reference surface WITHOUT the caps removal, changing
nothing else:

| | p50 | p90 | p95 |
|---|---|---|---|
| as protocol v1 measures it | 8.16 mm | 30.39 mm | 37.18 mm |
| reference surface not gutted | 1.33 mm | 7.45 mm | 9.31 mm |

The caps rule is right in principle: a distance to a surface the reference does not observe is not a
measurement. The defect is the asymmetry it produces on this data, not the idea. Note that 9.31 mm
still fails the 0.9419 mm threshold, so this does not turn a failure into a pass; it turns an
uninterpretable number into an interpretable one.

**Consequence for the controls.** The `shift` and `dilation` model-side controls are reported as not
behaving as required for bone and cartilage. They perturb the prediction by 3 px (2 mm) and require
p95 to get worse. A p95 already dominated by a 30 mm artefact cannot get meaningfully worse, so the
controls lose their discriminating power. Their failure is a symptom of the artefact, not independent
evidence about the model.

## 2. The model does under-segment bone, and that part is real

Band 2, reference bone 2,782,888 voxels:

- 467,506 missed (16.8 %). 450,550 of them, 96 %, are predicted as **muscle**.
- false positives only 20,206, all on reference muscle.
- the misses sit at median depth 2.3 mm inside the bone, p90 7.9 mm, max 15.5 mm: a rim plus interior.
- mean colour where bone is found (155, 97, 71); where it is missed (140, 93, 69).

Dice 0.9290 against a 0.9324 floor: it misses by 0.0034. This is a genuine, narrow failure of the
bone class and it is not explained away by section 1.

## 3. Muscle is strong

Dice 0.9718 against a 0.9105 floor, 0.5 % of the reference missed, and every missed voxel is
predicted as bone. Muscle fails only on the p95 of section 1.

## 4. Cartilage fails for real, and the wrong-neighbour control is what shows it

The wrong-neighbour baseline copies the Denver labels from 10 mm away and scores them on the same
slices. A model that cannot beat it has learned nothing useful about position.

| Class | model | wrong neighbour | model wins |
|---|---|---|---|
| bone | 0.9321 | 0.7804 | yes |
| muscle | 0.9712 | 0.8540 | yes |
| cartilage | 0.2405 | 0.3950 | **no** |

Cartilage loses to labels taken from a centimetre away. In band 2, where Denver has no cartilage at
all, the model still predicts 7,581 cartilage voxels, every one of them on reference bone: it is
calling a bone edge cartilage. The evaluator handled that run correctly, marking it
`false-positives-only` and keeping it out of the surface pool.

## 5. A reading error of ours, corrected

The first reading of this report said the wrong-neighbour control had not run, because its figures
are nested under `neighbour` and the top level was read instead. It ran for all three classes, and it
is the control that produced the clearest signal in section 4.

## 6. What this does to the protocol, stated plainly

A score now exists. Until this morning, `registry/machine-acceptance-protocol-v2.json` was planned as
a change made *before* any evaluation, which is the only kind of change to a frozen protocol that
costs nothing. That window has closed. From here:

- the path-string change that v2 was meant to carry still touches no criterion, but it can no longer
  be described as pre-score, and must be recorded as made after the `rgb-only` result;
- any change to the surface metric is now **post hoc**, whatever its merit. It must be labelled as a
  change made after seeing a failing score, the v1 result must stand as recorded, and a re-scored
  result must never be presented as if it had been produced under the original protocol.

Changing a yardstick that a result just failed is exactly what the freeze exists to prevent. The
argument in section 1 is that the yardstick is measuring something other than what it names, and that
argument is on the record before any new number is produced. It is for the auditor to judge, not for
this document to settle.

Nothing here is anatomy. No mesh, label or registration has been reviewed by anyone.
