# Registration into canonical space VHF-image-2022 (composition 0.4)

Canonical space: Aligned Visible Human Female image frame of the Denver 2022 release (Andreassen et al. 2022): +x subject right, +y anterior, +z superior, millimetres.
Status: defined from the Denver aligned image frame; verified against the NLM VHF CT header frame by a rigid same-donor pelvis fit (rotation 2.17 deg, free scale 1.0013, pelvis p95 4.7 mm).
Composition: {'hra-female': 786, 'nlm-vhf-ct': 101, 'denver-vhf': 128} meshes by source; {'hra-female-assembly': 786, 'VHF': 229} by donor.

## Same donor: NLM VHF fresh CT -> Denver frame

rigid (ICP, no scale) on the pelvis: CT hip bones and sacrum onto Denver hip bones and sacrum. Rotation 2.17 deg, scale fixed at 1.0, pelvis surface RMS 2.72 mm, p95 4.72 mm, Hausdorff 35.6 mm.
Frame verification: consistent (free-scale check 1.0013). The Denver aligned image frame and the NLM CT header frame agree in axis directions and millimetre units: the rigid pelvis fit needs a small rotation and a scale of 1 within one percent, and the same-donor pelvis surfaces agree to a few millimetres. The translation absorbs the different origins (vertex plane of the CT versus the Denver image origin). This verifies the canonical space against NLM image data; it does not review the anatomy of either segmentation.

| Structure | CT->Denver mean mm | p95 mm | Hausdorff mm |
| --- | ---: | ---: | ---: |
| Hip bones | 1.2 | 2.4 | 9.8 |
| Sacrum | 3.2 | 9.9 | 35.6 |
| Femur (left) | 3.5 | 8.8 | 12.4 |
| Femur (right) | 3.3 | 7.6 | 10.6 |

Femur pose change between acquisitions (own rigid fit versus pelvis transform): femur_left 2.9 deg, femur_right 1.4 deg.
CT labels are TotalSegmentator output (task total, Apache-2.0), not reviewed segmentations; Denver bones replace the CT hip bones, sacrum and femora in the composite.

## HRA viewer stage -> VHF-image-2022 canonical stage

similarity on bounding-box centres of six organ/pelvis proxies (targets: NLM VHF CT labels of the Denver donor). RMS 7.42 mm, maximum 10.31 mm, scale 0.994399.

| Source proxy | Target CT labels | Residual mm |
| --- | --- | ---: |
| HRA:VH_F_heart | heart | 10.31 |
| HRA:VH_F_liver | liver | 7.11 |
| HRA:VH_F_spleen | spleen | 5.53 |
| HRA:VH_F_kidney | kidney_left, kidney_right | 5.49 |
| HRA:VH_F_urinary_bladder | urinary_bladder | 8.60 |
| HRA:VH_F_pelvis | hip_left, hip_right, sacrum | 6.23 |

Cross-check, direct HRA pelvic landmark fit to Denver (not used): RMS 5.42 mm, maximum 8.70 mm, scale 0.963909. HRA pelvic landmarks fit the Denver pelvis closely (the HRA VH_F skeleton derives from the Visible Human Female), but the direct pelvic fit places HRA trunk organs away from the same-donor CT organs by the offsets listed; the organ-proxy fit is used for the composite.

| Organ proxy | Organ-fit offset vs CT mm | Direct pelvic offset vs CT mm |
| --- | ---: | ---: |
| HRA:VH_F_heart | 10.3 | 33.3 |
| HRA:VH_F_liver | 7.1 | 10.6 |
| HRA:VH_F_spleen | 5.5 | 19.5 |
| HRA:VH_F_kidney | 5.5 | 11.2 |
| HRA:VH_F_urinary_bladder | 8.6 | 16.0 |
| HRA:VH_F_pelvis | 6.2 | 3.5 |

- Bounding-box centres are geometric proxies, not anatomical landmarks.
- HRA is a multi-donor reference assembly; organ placement inside the VHF trunk is unreviewed.
- Targets are automatic CT labels (TotalSegmentator) of the VHF donor, not reviewed organ surfaces.

The head uses a separate bounding-box fit into the CT brain envelope. Its bounds containment is not an anatomical validation.

## Alternative source: TCIA 003 viewer stage -> VHF-image-2022 canonical stage (not composed)

Pelvic landmark similarity: RMS 12.07 mm, maximum 19.48 mm, 10 landmarks, scale 1.070485, volume factor 1.226710.
Pose check over all 18 pelvis, knee and ankle landmarks: RMS 43.57 mm, maximum 77.96 mm (not used). Knee and ankle residuals of 50-80 mm under one similarity indicate a different lower-limb pose (TCIA 003 knees flexed, shank inclined), not a frame error.

| Landmark | Side | Residual mm |
| --- | --- | ---: |
| femoral_head_centre | left | 7.95 |
| anterior_superior_iliac_spine | left | 13.52 |
| ischial_tuberosity | left | 5.90 |
| iliac_crest_apex | left | 19.48 |
| pubic_symphysis_facet | left | 6.12 |
| femoral_head_centre | right | 7.54 |
| anterior_superior_iliac_spine | right | 14.62 |
| ischial_tuberosity | right | 11.42 |
| iliac_crest_apex | right | 16.84 |
| pubic_symphysis_facet | right | 8.70 |

### Bone-to-bone surface distances, Denver vs transformed TCIA 003

| Structure | Denver->TCIA mean mm | p95 mm | Hausdorff mm | Denver inside TCIA envelope (5 mm) | Shape p95 mm after per-bone rigid ICP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hip bones | 3.5 | 7.6 | 13.9 | 0.999 | 7.9 |
| Femur (left) | 33.9 | 82.1 | 99.9 | 0.878 | 11.9 |
| Femur (right) | 50.5 | 112.8 | 131.2 | 0.837 | 10.3 |
| Tibia (left) | 55.8 | 79.6 | 91.5 | 0.547 | 14.0 |
| Tibia (right) | 87.9 | 112.4 | 126.5 | 0.122 | 11.2 |
| Fibula (left) | 59.9 | 85.1 | 95.8 | 0.013 | 12.0 |
| Fibula (right) | 99.8 | 125.1 | 137.5 | 0.000 | 7.8 |
| Sacrum and coccyx (one-directional) | 3.4 | 8.3 | 18.6 | n/a | n/a |

Distances are sampled nearest-neighbour values. In-frame femur, tibia and fibula distances reflect the TCIA 003 lower-limb pose, not a frame error; per-bone rigid ICP compares donor bone shape only.

- Landmarks are automatic geometric rules on grouped CT labels split by connected components or midline sign; no anatomist has confirmed them.
- Different donors (VHF, 59 years; TCIA 003, 26 years, 1.70 m) and poses; a similarity cannot remove pose differences.
- Since composition 0.4 the composite uses the same-donor NLM CT instead of TCIA 003; this fit only positions the alternative source.

## Acceptance

- nlm_ct_pelvis_rigid_p95_below_5_mm: met (value_mm 4.717)
- nlm_ct_frame_scale_within_1_percent: met (value 1.001)
- nlm_ct_frame_rotation_below_5_deg: met (value_deg 2.165)
- tcia_pelvic_landmark_rms_below_15_mm: met (value_mm 12.075) Alternative source (TCIA 003), not composed.
- tcia_all_lower_limb_landmark_rms_below_15_mm: not met (value_mm 43.569) Not achievable with one similarity because of the TCIA 003 knee flexion; lower-limb bones come from Denver only.
- denver_hip_bones_inside_tcia_pelvis_envelope: not met (fraction_inside 0.999, max_excess_mm 5.920)
- hra_organ_proxy_rms_below_30_mm: met (value_mm 7.421)
- manual landmark review: pending; anatomical review: pending.

All landmarks are automatic geometric rules (`scripts/extract-landmarks.py`) or bounding-box proxies; manual review is pending. Matrices, landmarks and surface distances are in `registration-report.json` and `transforms/`.
