# BMFToolkit versus Denver VHF (same donor, not shipped)

zlib is permissive and OSI-approved, but its text addresses software; whether the authors intend it to cover the mesh data is not stated. Meshes stay out of the shipped atlases until the authors confirm; see docs/LICENSING.md for the prepared request.

| BMF asset | Geometry | Denver asset | p95 mm | Hausdorff mm | Volume ratio |
| --- | --- | --- | ---: | ---: | ---: |
| Sacrum | symmetrized | DENVER:VHF:Left_Bone_Sacrum | 15.6 | 22.7 | 1.270 |
| PelvisR | segmented_right | DENVER:VHF:Right_Bone_Pelvis | 1.7 | 4.0 | 0.956 |
| PelvisL | mirrored_from_right | DENVER:VHF:Left_Bone_Pelvis | 3.6 | 9.2 | 0.956 |
| FemurR | segmented_right | DENVER:VHF:Right_Bone_Femur | 4.7 | 6.8 | 1.164 |
| FemurL | mirrored_from_right | DENVER:VHF:Left_Bone_Femur | 3.7 | 8.0 | 1.106 |
| PatellaR | segmented_right | DENVER:VHF:Right_Bone_Patella | 3.1 | 4.4 | 1.230 |
| PatellaL | mirrored_from_right | DENVER:VHF:Left_Bone_Patella | 3.1 | 4.7 | 1.201 |
| TibiaR | segmented_right | DENVER:VHF:Right_Bone_Tibia | 2.4 | 4.2 | 1.135 |
| TibiaL | mirrored_from_right | DENVER:VHF:Left_Bone_Tibia | 3.9 | 7.9 | 1.117 |
| FibulaR | segmented_right | DENVER:VHF:Right_Bone_Fibula | 2.5 | 5.0 | 1.479 |
| FibulaL | mirrored_from_right | DENVER:VHF:Left_Bone_Fibula | 4.3 | 7.8 | 1.548 |
| TalusR | segmented_right | DENVER:VHF:Right_Bone_Talus | 2.2 | 3.8 | 1.055 |
| TalusL | mirrored_from_right | DENVER:VHF:Left_Bone_Talus | 1.3 | 3.9 | 0.964 |
| CalcaneusR | segmented_right | DENVER:VHF:Right_Bone_Calcaneous | 1.2 | 3.0 | 0.970 |
| CalcaneusL | mirrored_from_right | DENVER:VHF:Left_Bone_Calcaneous | 1.3 | 4.2 | 0.992 |
| NavicularR | segmented_right | DENVER:VHF:Right_Bone_Navicular | 1.0 | 2.4 | 0.995 |
| NavicularL | mirrored_from_right | DENVER:VHF:Left_Bone_Navicular | 1.1 | 2.1 | 0.916 |
| CuboidR | segmented_right | DENVER:VHF:Right_Bone_Cuboid | 1.0 | 2.3 | 0.947 |
| CuboidL | mirrored_from_right | DENVER:VHF:Left_Bone_Cuboid | 2.2 | 3.1 | 0.977 |
| MedialCuneiformR | segmented_right | DENVER:VHF:Right_Bone_MedialCuneiform | 1.0 | 2.1 | 0.923 |
| MedialCuneiformL | mirrored_from_right | DENVER:VHF:Left_Bone_MedialCuneiform | 1.0 | 1.9 | 0.952 |
| IntermediateCuneiformR | segmented_right | DENVER:VHF:Right_Bone_IntermediateCuneiform | 1.1 | 2.2 | 0.903 |
| IntermediateCuneiformL | mirrored_from_right | DENVER:VHF:Left_Bone_IntermediateCuneiform | 1.6 | 2.7 | 0.900 |
| LateralCuneiformR | segmented_right | DENVER:VHF:Right_Bone_LateralCuneiform | 0.9 | 1.8 | 0.968 |
| LateralCuneiformL | mirrored_from_right | DENVER:VHF:Left_Bone_LateralCuneiform | 2.6 | 3.9 | 1.046 |
| PhalangesR (set of 14 BMF meshes) | segmented_right | DENVER:VHF:Right_Bone_Phalanges | 6.0 | 30.3 | 0.259 |
| PhalangesL (set of 14 BMF meshes) | mirrored_from_right | DENVER:VHF:Left_Bone_Phalanges | 6.4 | 33.1 | 0.244 |

Median p95: segmented right bones 1.7 mm, mirrored left bones 2.6 mm. Same donor, different modality (CT versus cryosection) and processing (BMF neutral-pose correction, smoothing, mirroring). Small residuals after rigid ICP support that both sets describe the same bones; the mirrored left side should show larger residuals than the segmented right side where the donor is asymmetric.
