# Plan: AI segmentation of the Visible Human Female cryosections

Status: proposal (5 September 2026). A project of its own, separate from the atlas; it delivers a new source `nlm-vhf-cryo` to the atlas.

## 1. Goal

Obtain, for the same donor as Denver (Visible Human Female, NLM), labels for the trunk, upper limb, hands, head and neck from the colour photographs of the cryosections (0.33 mm isotropic), under a free licence and with recorded anatomical review. Today those regions come from a 1 mm CT labelled by AI (114 coarse labels) and the ulna, radius and hands are missing.

Expected result: a 3D label map (NIfTI) over the cryosection volume aligned to the `VHF-image-2022` frame, with 200 to 300 structures, plus the derived meshes with per-structure provenance.

## 2. What already exists (search of 5 September 2026)

| Work | What it did | Licence | Use for us |
|---|---|---|---|
| NLM Visible Human Female (1995) | 5,189 colour photographs at 0.33 mm (40 GB), CT and MRI. No labels. | NLM terms, no licence since 2019 | Input data. Direct download. |
| Denver, Andreassen et al. 2022 (`digitalcommons.du.edu/visiblehuman/1`) | Pelvis to feet: 128 structures hand-painted on the cryosections. Also publishes the **aligned cryosections as DICOM (485 MB, pelvis to feet)** and the **CT aligned to the cryosection frame (316 MB, whole body)**. | CC BY 4.0 | Training and validation labels of the same donor. The aligned CT cross-checks our rigid registration (rotation 2.17°). |
| NEVA Electromagnetics, VHP-Female v2.2 / v3 / 5.0 and the "Nelly" phantom (Makarov, Noetscher et al., PLOS One 2021) | Already segmented the whole VHF body from the cryosections: 249 structures (v5.0 up to 270 parts), stated accuracy 2 to 7 mm, reviewed by anatomists. | v2.2 free for registered researchers; v3+ commercial. Not an open licence; no redistribution. | Proof of feasibility and comparison reference. Cannot be incorporated into the atlas. Contact them about an open licence for v2.2. |
| Voxel-Man, Segmented Inner Organs (Visible Human **Male**) | Thorax and abdomen of the male, more than 200 objects, 1 mm voxels. | CC BY 4.0 | Auxiliary training data for organ colour and texture in cryosections; other sex and other donor. |
| Visible Korean Human, Chinese Visible Human | Own cryosections with partial labels (VKH: one slice in five). | Not open | Methodological reference only. |
| AI segmentation of cryosections (stacked autoencoders on CVH brain 2016; U-Net on VKH head 2017; nnU-Net on mouse cryosections 2022) | Show that 2D/3D networks segment cryosection colour with good accuracy, but on small regions. | Various | Methodological basis. No published whole-body VHF work with AI and free labels. |
| MedSAM2 (2025), SegmentWithSAM (3D Slicer), Medical-SAM2 GUI (Napari, 2026) | Propagate one slice annotation through a whole volume with memory; cut annotation time by 85 %. | Apache-2.0 / MIT (check the weights) | Semi-automatic annotation tool for the anatomist. |

Conclusion: the idea is feasible and nobody has published free whole-body labels of the VHF. NEVA did it under a closed licence. The open gap is exactly this project.

## 3. Data

1. NLM photographs: `Female-Images/Fullcolor/` (raw24, 2048 x 1216 x 3 bytes per slice, 5,189 slices). Download with a SHA-256 manifest (extend `scripts/fetch-nlm-vhf.py`).
2. Alignment: the original slices have small shifts between them. Denver publishes the aligned slices from pelvis to feet and its method (`github.com/thor-andreassen/femors`). Reproduce their alignment for the rest of the body, or register each slice to Denver's aligned whole-body CT as a low-resolution guide.
3. Training labels: Denver's 128 masks (`Original Segmentation Label Maps`, 2.1 GB) on the same slices.
4. Additional reference labels: our 114 TotalSegmentator labels of the CT, carried into the cryosection frame with `nlm-ct-to-vhf` (resampled from 1 mm to 0.33 mm). They serve as weak labels for trunk organs.

## 4. Method by phase

### Phase A. Aligned cryosection volume (2 to 3 weeks)
- Download and verify the 5,189 slices. Build an RGB volume in the `VHF-image-2022` frame (extension of `build-nlm-vhf-volume.py`).
- Validate the alignment against Denver's aligned slices (pelvis to feet): mean difference per slice < 1 pixel.
- Criterion: Denver's 128 masks fit our volume with Dice > 0.98 against the voxelised Denver meshes.

### Phase B. Bootstrap model (3 to 4 weeks, GPU)
- Train nnU-Net (2D and 3D, RGB input) with the 128 Denver labels, cross-validated by slice.
- Internal target: mean Dice > 0.90 on bones and > 0.85 on muscles on unseen leg slices.
- Apply the model to arms and trunk to obtain proposals for bone, muscle, cartilage and fat. It will not give new names; it will give tissue classes.

### Phase C. Naming and assisted annotation (6 to 10 weeks, anatomist)
- Tool: MedSAM2 in Napari or 3D Slicer with slice-to-slice propagation. The anatomist places a box or a point on one slice every 5 to 10 mm; the model propagates.
- Structure priority: arm and hand bones (28 per side), individual vertebrae and ribs, trunk organs, trunk and arm muscles, head and neck.
- Every structure receives UBERON/FMA through the existing crosswalk (`scripts/build-crosswalk.py`) and a status in `registry/review-status.json`.
- Weak CT labels (TotalSegmentator) as initialisation for organs; the anatomist corrects on the colour photograph.

### Phase D. Final model and quality control (3 weeks)
- Retrain nnU-Net with Denver + new annotations. Final whole-body prediction.
- Compare with: Denver meshes (same donor, pelvis to feet), CT labels of the same donor (trunk), NEVA v2.2 phantom if its licence allows the comparison (distances only, no redistribution).
- Criteria: Dice > 0.90 on bones against Denver on test slices; surface p95 < 2 mm between cryosection bone and CT bone of the same donor after the rigid registration already measured; no structure published without an anatomist's `reviewed` status.

### Phase E. Integration into the atlas (1 week)
- New source `nlm-vhf-cryo` through the current pipeline (`ingest`, `optimize`, `compress`, registration, crosswalk, composition, QA, validators).
- In the composite, the cryosection replaces the CT of the same donor where a review exists; the CT stays as an alternative.

## 5. Resources

- GPU: 3D nnU-Net at 0.33 mm needs a lot of memory. Realistic option: 2D per slice at full resolution and 3D at 1 mm, fused. One 24 GB GPU; days of training. Not feasible without a GPU.
- Disk: 40 GB of photographs + 100 to 150 GB of volumes and predictions.
- People: one anatomist or anatomist in training with 60 to 100 hours of annotation and review; one engineer for the pipeline.
- Licences: NLM input (mandatory attribution), Denver CC BY 4.0, nnU-Net Apache-2.0, MedSAM2 Apache-2.0 (verify the weights licence before use), Voxel-Man SIO CC BY 4.0. Outputs are published CC BY 4.0 with the NLM attribution.

## 6. Risks

- Alignment of the trunk slices: without Denver's alignment it must be reproduced; a 1 pixel (0.33 mm) error is acceptable, an error of several slices is not.
- Freezing and cutting artefacts (ice, extravasated blood, lost cuts) confuse the network; Denver corrected them by hand.
- Naming: the network separates tissues, it does not name individual bones; names require human annotation.
- NEVA may hold rights over its segmentation but not over the photographs nor over our labels; copy nothing from their models.

## 7. First concrete milestone

Download the slices from pelvis to feet, align, voxelise the 128 Denver meshes and train 2D nnU-Net. Deliverable: Dice per structure in cross-validation and a prediction over 200 trunk slices for visual inspection. Without this milestone the rest is not planned.

## Sources consulted

- NLM Visible Human Project, data and index: https://www.nlm.nih.gov/research/visible/getting_data.html
- Denver, Visible Human Female (aligned cryosections, aligned CT, masks, STL): https://digitalcommons.du.edu/visiblehuman/1/ ; paper https://www.nature.com/articles/s41597-022-01905-2 ; code https://github.com/thor-andreassen/femors ; SimTK https://simtk.org/projects/3d-vh-geometry
- NEVA Electromagnetics VHP-Female: https://www.nevaelectromagnetics.com/vhp-female-5-0 ; Nelly phantom, PLOS One 2021: https://pmc.ncbi.nlm.nih.gov/articles/PMC8664205/ ; Sandia IMR note: https://www.sandia.gov/imr/Papers/IMR23_ResearchNote8_Yanamadala.pdf
- Voxel-Man Segmented Inner Organs (CC BY 4.0, male): https://www.voxel-man.com/segmented-inner-organs-of-the-visible-human/
- AI segmentation of cryosections: CVH brain (SAE) https://pmc.ncbi.nlm.nih.gov/articles/PMC4807075 ; VKH head (deep networks) https://arxiv.org/pdf/1703.04967 ; mouse cryosection nnU-Net https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9452525/
- Annotation tools: MedSAM2 https://opencv.org/blog/medsam2/ ; Medical-SAM2 GUI (Napari) https://arxiv.org/html/2602.22649v1 ; SegmentWithSAM (3D Slicer) https://www.researchgate.net/publication/383461223 ; interactive 3D SAM 2 https://arxiv.org/pdf/2408.02635
- nnU-Net: https://www.nature.com/articles/s41592-020-01008-z
