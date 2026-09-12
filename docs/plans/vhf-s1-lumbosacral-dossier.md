# Lumbosacral `S1` dossier: what the VHF donor has below the last rib-bearing vertebra

Opened 12 September 2026. Purpose: gather every piece of evidence about the lumbosacral transition of the
Visible Human Female donor, so the question is either resolved from documentation and automatic checks or
handed to an anatomist with the evidence assembled. It does not block any other work item. Nothing here
changes `name_status: pending` on any instance until a decision is recorded in `registry/review-status.json`.

## 1. The question

Between the last rib-bearing vertebra (instance V19, candidate T12) and the sacrum, both CTs show six
lumbar-type vertebral bodies (instances V20 to V25). Below them TotalSegmentator alone labels a further body
of about 49 mL as `S1`, which MOOSE labels sacrum and Skellytour PELVIS (review-only instance, not meshed).
Three readings are possible and the atlas must not choose by default:

| Reading | What V20 to V25 are | What the `S1` body is | Consequence for names |
|---|---|---|---|
| A. Six lumbar vertebrae | L1 to L6 | first sacral segment of a normal sacrum | HRA chain by order is right; V25 = L6 |
| B. Lumbarised S1 | L1 to L5 + lumbarised S1 | S2 (sacrum with one fewer fused segment) | V25 = "S1 (lumbarised)"; sacrum has four fused segments |
| C. Thoracolumbar shift | T13 + L1 to L5, or a rib-less T12 | S1 | V19/V20 names shift; rib count (12 per side, unanimous) argues against a 13th rib-bearing vertebra but not against a rib-less transitional vertebra |

Counting alone cannot separate A from B: both give 25 free vertebrae. The separation needs the morphology of
V25 (transverse processes, articulation with the ilium, disc height to the sacrum) and the number of fused
sacral segments.

## 2. Evidence already in hand

- Both CTs, three models, instance consensus: 7 + 12 + 6 free bodies and a sacrum (`generated/ct-vertebra-instances-{nlm,denver}.json`, `lumbar_type_block_below_T12`). Ribs: 12 per side on both CTs, all three models (`generated/ct-rib-instances-nlm-{left,right}.json`).
- Same-donor HRA skeleton (`public/atlases/hra-female.json`, `VH_F_lumbar_vertebra_1..6`): six lumbar vertebrae and a fused sacrum; by-order z offsets within 7 mm on the NLM CT (`hra_same_donor_evidence`).
- NIH 3D entry 3DPX-020988 states "The Visible Human Female has 6 lumbar vertebrae" (text recorded in the instance table; the entry does not say how the sacrum was counted).
- Denver sacrum mesh (`DENVER:VHF:Sacrum`, measured from the cryosections): its top surface lies 14.5 mm below the bottom of the consensus column (`generated/anatomy-qa.json`, bounding boxes). The consensus sacrum differs from the Denver sacrum by 9.8 mm p95 under the pelvis registration, mostly in extent and at the coccyx.
- TotalSegmentator `S1` body: about 49 mL, absorbed by the sacrum label of MOOSE and the PELVIS label of Skellytour (`review_only_instances` in `public/atlases/ct-consensus.json`).

## 3. Checks that need no anatomist (to run, in order)

1. **Denver sacrum segment count.** The Denver sacrum mesh comes from the cryosections. Count the fused segments from its anterior surface (transverse ridges, anterior sacral foramina pairs) on the mesh and on the Denver aligned cryosection DICOM already downloaded (`data/raw/denver/aligned-cryosection-dicom.zip`). Four pairs of foramina = five fused segments (reading A or C); three pairs = four segments (reading B).
2. **Does the TotalSegmentator `S1` body lie inside the Denver sacrum?** Transform the `S1` review mask through `nlm-ct-to-vhf` and measure its overlap with the Denver sacrum mesh. Inside: it is the first sacral segment of the Denver sacrum (A or C). Above and separate, with a disc space to the sacrum on the CT: a free segment the cryosection model fused (B).
3. **V25 morphology on the CT.** Transverse process shape and any articulation or fusion with the ilium (sacralisation signs), disc height V25/sacrum versus V24/V25, on both CTs. Iliolumbar contact argues for B.
4. **Rib-less transitional vertebra check for C.** V19 carries ribs on both sides (rib instances RL12 / RR12 attach to it: verify by adjacency of the rib and vertebra consensus masks). If the ribs attach to V19, C requires V19 to be T12 and V20 to be a rib-less T13 or L1; the T13 case would need a 13th thoracic pattern (costal facets on V20), which the CT can show.
5. **HRA chain reading.** Record how the HRA/NIH model authors counted (their sacrum has how many segments?) from the published model, not from correspondence.

Deliverable: `generated/s1-dossier.json` with each check, its measurement, and which readings it excludes. Only if a
single reading survives is a name proposed, and even then it is written as `name_status: documented-candidate`,
not as a decision; the anatomist pass converts it to `inspected` or rejects it.

## 4. What stays fixed whatever the outcome

Geometric ids V01..V25 and the per-model alternatives; `hra_name_by_order` as evidence; the sacrum from Denver in
the composite; the 12 + 12 rib count; the rule that no reading is imposed by convention (24/25 vertebrae, five/six
lumbar). Contact with HRA, Denver, NIH or forums needs a separate authorisation.
