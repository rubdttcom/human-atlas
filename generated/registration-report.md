# Experimental registration

Torso RMS: 27.21 mm. Maximum residual: 35.40 mm.
Global scale: 0.997140. Volume factor: 0.991444.

| Source proxy | Target label | Residual mm |
| --- | --- | ---: |
| HRA:VH_F_heart | Heart | 30.64 |
| HRA:VH_F_liver | Liver | 30.55 |
| HRA:VH_F_spleen | Spleen | 8.56 |
| HRA:VH_F_kidney | Kidneys | 35.40 |
| HRA:VH_F_urinary_bladder | Bladder | 17.16 |
| HRA:VH_F_pelvis | Pelvis | 30.81 |

## Denver VHF viewer stage -> TCIA 003 viewer stage

RMS: 28.13 mm. Maximum residual: 40.91 mm. Scale: 0.981095. Volume factor: 0.944352.

| Source proxy | Target label | Residual mm |
| --- | --- | ---: |
| Pelvis, sacrum and coccyx | Pelvis | 33.05 |
| Femur | Femur | 12.48 |
| Tibia | Tibia | 9.05 |
| Fibula | Fibula | 14.15 |
| Patella | Patella | 40.91 |
| Tarsal bones | Tarsal | 39.28 |

- Bounding-box centres of grouped bones are geometric proxies, not anatomical landmarks.
- TCIA grouped labels may include or exclude the sacrum; the pelvis proxy pairing is unreviewed.
- Different donors (VHF, 59 years; TCIA 003, 26 years) and poses; joint spaces and soft-tissue overlap are unreviewed.
- Denver "Phalanges" spans about 149 mm antero-posteriorly and probably includes the metatarsals; TCIA metatarsal and toe labels are therefore excluded, unreviewed.

The head uses a separate bounding-box fit. Its bounds containment is not an anatomical validation.
No Hausdorff distance, manual landmarks or cervical continuity validation has been completed.
Matrices and regional scale changes are in `registration-report.json`. The frame is TCIA 003, not canonical VHF.
