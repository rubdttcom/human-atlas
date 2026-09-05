# Implementation status

This is an implementation of `docs/plans/female-open-human-atlas-plan.md` up to composition 0.4
(2026-09-05). The full objective remains active. Do not interpret working rendering,
passing validators or licence checks as validation of a complete anatomical atlas: no
anatomist has reviewed any mesh, landmark or registration.

## Authoritative state

- Local fork: `ashemag/human-atlas`, base `7a383d3ee2759e3ddf157c704fb8814fd0c50bcb`, branch `female-open-atlas`.
- HRA Female v1.5: 888 meshes restored from `d72b4f6db42e41a8db84b1c19ff6d86ee7b65284`. Reference assembly, individual donors unresolved.
- BodyParts3D 4.0: 2,234 male reference meshes, selectable separately. Not used in the female composition. Its lateralized FMA identifiers now resolve through the crosswalk, so 1,221 of its meshes merge with female entries for comparison.
- TCIA Healthy Total Body CTs: subject 003, female, 26 years. 36 labels converted (1,049,570 optimized triangles). Registered to VHF by a pelvic-landmark similarity (RMS 12.07 mm) as an alternative source; no longer part of the composite (different donor, flexed knees).
- Denver VHF 2022 (`digitalcommons.du.edu/visiblehuman/1`): 128 final STL meshes (28 bones, 76 muscles, 16 cartilages, 8 ligaments), CC BY 4.0, native aligned VHF image frame, identity in the canonical space.
- NLM Visible Human Female fresh CT (new): terms verified (no licence since July 2019; attribution "Courtesy of the U.S. National Library of Medicine"), 1,734 GE slices and headers downloaded with SHA-256 (`data/raw/nlm-vhf/`), assembled into one 512 x 512 x 1734 RAS volume at 0.9375 x 0.9375 x 1 mm (`scripts/build-nlm-vhf-volume.py`; two exams, junction shift measured at 5.6 x 3.8 mm and recorded). Segmented with TotalSegmentator 2.18.0 `total` (Apache-2.0, CPU, 1.5 mm): 114 of 117 labels present. Stray islands below 5 % of each label's main component are removed and counted.
- Canonical space `VHF-image-2022` (`transforms/canonical-space.json`): the Denver aligned VHF image frame, now verified against the NLM CT header frame. Rigid same-donor registration of the CT hip bones and sacrum onto the Denver pelvis (`transforms/nlm-ct-to-vhf.json`): rotation 2.17 deg, free-scale check 1.0013, pelvis surface p95 4.72 mm (hip bones 2.4 mm, sacrum 9.8 mm, femora 7.5 to 8.7 mm under the pelvis transform; own femur fits 3.4 to 4.4 mm with hip pose changes of 1.6 and 3.0 deg between acquisitions). `generated/nlm-ct-registration.json`.
- New source `nlm-vhf-ct`: 114 meshes, 1,431,628 optimized triangles, 14 MB gzip, natively in the canonical stage (voxel -> CT RAS -> `nlm-ct-to-vhf` -> stage). Automatic labels, unreviewed.
- Reviewed ontology crosswalk (`registry/crosswalk-proposals.json` -> `scripts/build-crosswalk.py` -> `registry/ontology-crosswalk-reviewed.json`): every entry carries the OLS record (IRI, label, synonyms, xrefs, definition) and match type. Applied: Denver 69/69, TCIA 35/36, NLM CT 114/117, HRA lateralized FMA 176/201, BodyParts3D lateralized FMA 1,221/1,360; 168 unresolved or uncertain entries keep their source identifiers. 1,712 meshes carry a crosswalk resolution; 248 catalog entries now have several sources; 22 entries merge Denver with HRA (femur, tibia, fibula, patella, sacrum, coccyx, knee cartilage and ligaments, lower-limb muscles). Anatomist review pending for every equivalence.
- Experimental composition 0.4: 1,015 meshes, 3,219,937 triangles, 40 MB gzip. Denver (128, identity) + NLM VHF CT (101 labels; Denver replaces the CT hip bones, sacrum, femora and gluteal/iliopsoas labels) + HRA detail (786 meshes; skeleton, skin, lower-limb muscles and organs already covered by a same-donor CT label excluded). HRA fitted by a similarity on six organ bounding-box proxies onto the CT organs: RMS 7.42 mm (was 29.1 mm through TCIA); head by a bounding-box fit into the CT brain envelope. 229 composite meshes come from the single VHF donor; 786 from the HRA assembly.
- Bone landmarks (`scripts/extract-landmarks.py`, `transforms/landmarks/*.json`): 18 per source (Denver, TCIA 003, HRA), automatic geometric rules, `manual_review: pending`. The viewer's Registration review panel draws the pairs and exports reviewer decisions to `landmark-review.json` (intake: `registry/landmark-review.json`).
- BMFToolkit: LICENSE is zlib with no data carve-out (Zenodo `other-open`); request to the authors drafted in `docs/LICENSING.md`, not sent. Compared bone by bone with Denver (`generated/bmftoolkit-comparison.json`): segmented right bones median p95 1.7 mm, mirrored left 2.6 mm, symmetrized sacrum 15.6 mm. Not shipped.
- Anatomy QA (`scripts/qa-anatomy.py`, `generated/anatomy-qa.json`): self-intersecting triangle pairs per mesh (edge-triangle tests), connected components and outlier components, composite bounding-box continuity. Meshes with self-intersections: Denver 1 of 128, TCIA 36 of 36 (voxel meshes), NLM CT 101 of 114, HRA 89 of 888, composite 175 of 1,015, BodyParts3D 2,060 of 2,234. Outlier components: TCIA 16 labels (`Toes` above the head), NLM CT 1, HRA 4, composite 5. Continuity: HRA head structures overlap the top of the CT vertebral column by 3.7 mm and the HRA brain lies inside the CT skull box; the CT vertebral column (S1 included) ends 39 mm below the Denver sacrum top. Review decisions live in `registry/review-status.json` (default `pending`, three known issues recorded).
- Licence verification 2026-09-05 (`datasets.csv`): NLM terms; SPIDER, OpenEar, HiP-CT CC BY 4.0 (specimen selection pending); Teeth3DS CC BY-NC-ND (cannot be shipped); Z-Anatomy CC BY-SA (male-derived, share-alike target only); SPARC per dataset; BMFToolkit zlib scope unconfirmed.
- UI: sources HRA, TCIA, Denver, NLM VHF CT, composite, BodyParts3D; donor filter; registration review panel with landmark overlay and exportable decisions; side-by-side source comparison for structures with alternatives; coverage filters for multi-source, partial (grouped label) and crosswalk-resolved entries; ontology term and mapping in every provenance panel.

## Plan audit

| Phase | Evidence | Remaining work |
| --- | --- | --- |
| 0 Survey | `datasets.csv`, 15 sources, licences verified with evidence URLs and dates for 13 | BMFToolkit data scope (authors); Open3Dmodel and AnatomyTool per-asset terms. |
| 1 Ontology | Reviewed crosswalk with OLS evidence for Denver, TCIA, NLM CT, HRA and BodyParts3D lateralized terms | Anatomist review of equivalences; 168 unresolved entries; TA2 import; full UBERON universe beyond the imported union. |
| 2 Coverage | Coverage matrix with individual, grouped and partial kinds, per-source candidates, 248 multi-source entries | Register candidate availability outside imported data (SPIDER, OpenEar, HiP-CT specimens). |
| 3 VHF base | Canonical space verified against NLM CT headers (rotation 2.2 deg, scale 1.001); trunk, upper limb and head of the same donor from the NLM CT labels; Denver lower limb | Hands, forearm bones, patella, tibia, fibula and feet of the VHF donor from CT need the licensed TotalSegmentator `appendicular_bones` task (not usable) or another segmenter; cryosection-based trunk segmentation; anatomist landmark review. |
| 4 CT scaffold | TCIA 003 (alternative source), NLM VHF CT (composite trunk) | Mask review; CT femur pose differs from the cryosections by 1.6 to 3.0 deg (Denver bones used). |
| 5 Specialized | Licences and specimen metadata verified for SPIDER, OpenEar, HiP-CT, Teeth3DS, SPARC | Specimen selection with documented sex and frame; import as overlays. |
| 6 Fallback | BodyParts3D comparison reference merged through the crosswalk; Z-Anatomy audited (CC BY-SA, male-derived) | None planned for the open-clean target. |
| 7 QA | Geometry, self-intersections, components, outliers, continuity, licence checks, registration evidence, review registries | Anatomist review of every mesh, landmark and fit; `registry/review-status.json` is empty except known issues. |
| 8 Web atlas | Six sources, donor filter, registration review, comparison, coverage filters, provenance with ontology | Landmark editing in 3D (decisions only today); multiresolution overlays for future specialist sources. |

## Known limitations

- Every registration is automatic. The same-donor CT fit is rigid and tight at the pelvis (p95 4.7 mm) but the CT sacrum differs from the Denver sacrum by 9.8 mm p95 (extent and coccyx), and the femora moved 1.6 to 3.0 deg at the hip between acquisitions; the CT trunk above the pelvis inherits any spinal posture difference between the fresh CT (on the table) and the frozen block, which is unmeasured.
- The two CT exams (vertex to thigh, thigh to feet) were stacked with a 1 mm continuity assumption; the measured in-plane shift at the junction (5.6 x 3.8 mm) is recorded, not corrected. Only exam 370 (trunk) enters the composite; the exam 371 legs are covered by Denver.
- TotalSegmentator labels are model output on a 1993 cadaver CT; boundaries, missing labels (prostate, kidney cysts, portal vein union) and label extents are unreviewed. Stray islands below 5 % of a label were removed and counted.
- HRA organs are placed by a six-proxy similarity (RMS 7.4 mm on bounding-box centres), which does not validate organ shape or position; HRA organs with the same term as a CT label are dropped, so the composite mixes one measured donor with a reference assembly.
- The composite has no VHF hands, forearm bones, patellae, tibiae, fibulae or feet from CT: those come from Denver (feet, patellae, tibiae, fibulae) or are missing (hands, radius, ulna). TCIA forearm bones are not composed.
- Landmarks are automatic geometric rules; slab centroids sit up to 6.6 mm off the surface. Manual landmark review is pending.
- CT tissue depots (TCIA) and CT muscle compartments (NLM autochthon) contain nonmanifold edges or self-intersections; they are preserved as labelled compartments, not repaired.
- `Toes` (TCIA) has outlying geometry above the head; it is flagged in `generated/anatomy-qa.json` and excluded from the composite.
- Source-local labels resolve to UBERON/FMA by exact label or synonym with OLS evidence, but no anatomist has confirmed the equivalences; 168 entries remain unresolved.
- Upstream npm installation reports 11 vulnerabilities. Dependency remediation has not yet been evaluated.

## Next work

Order and acceptance criteria are in `docs/plans/female-open-human-atlas-plan.md`, section 29.

1. Anatomist review: landmarks (viewer export -> `registry/landmark-review.json`), CT label boundaries, HRA placement; then refit from confirmed landmarks only.
2. VHF appendicular bones, hands, trunk and head from the colour cryosections: separate project, see `docs/plans/vhf-cryosection-segmentation-plan.md` (Denver also publishes the full-body CT aligned to the cryosection frame, a cross-check for `nlm-ct-to-vhf`). Measure the fresh-CT versus frozen-block trunk posture (spine landmarks).
3. BMFToolkit: send the drafted licence request; import as a comparison source if the authors confirm.
4. Specialist overlays: select one female SPIDER lumbar study and one OpenEar specimen with documented sex; import as registered overlays in their own frames.
5. Ontology: review the 168 unresolved crosswalk entries; import TA2 identifiers.
6. Dependency remediation for the upstream npm vulnerabilities.

All large input data are outside Git under `data/raw/`, `data/derived/` or `sources/`. Nothing has
been published, deployed externally, or represented as anatomically validated.
