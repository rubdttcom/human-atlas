# Anatomy data attribution

BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International.

- License: https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html (updated 2025-02-27)
- Dataset: https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html
- License terms: https://creativecommons.org/licenses/by/4.0/
- Source geometry: `isa_BP3D_4.0_obj_99.zip`, BodyParts3D 4.0.
- English names and relationships: IS-A and PART-OF concept, element, and inclusion tables from the same archive.
- Publication: Mitsuhashi et al. (2009), BodyParts3D: 3D structure database for anatomical concepts. https://doi.org/10.1093/nar/gkn613

Adaptations: axes and units converted from millimeters/Z-up to meters/Y-up; translated to rest at the stage; geometry simplified using meshoptimizer with 0.2% relative error limit per structure; normals quantized to signed 16-bit; packed into binary chunks; curated display system groupings and colors. The source contains 2,234 individual OBJ meshes; all remain represented. The combined hierarchy contains 3,432 named FMA concepts, which may reference multiple meshes. Original source identity is preserved in the manifest.

Source OBJ comments mention an older CC BY-SA 2.1 Japan license. The official current database license linked above supersedes that legacy text and explicitly permits redistribution and adaptation under CC BY 4.0.

BodyParts3D represents an adult male reference anatomy based on TARO MRI and anatomical illustration refinements. It is not a complete model of every possible human anatomical structure or variation. This interface is educational and is not a clinical tool.

## Female reference assets (restored in this local fork)

Female reference anatomy: Kristen Browne and Heidi Schlehlein, Human Reference Atlas / HuBMAP, *3D Reference Organ Set for Female v1.5* (2023). CC BY 4.0. Geometry adapted for this viewer. Restored from human-atlas revision `d72b4f6db42e41a8db84b1c19ff6d86ee7b65284`.

- Source DOI: https://doi.org/10.48539/HBM352.BTSQ.586
- Dataset: https://lod.humanatlas.io/ref-organ/united-female/v1.5
- Original GLB: https://cdn.humanatlas.io/digital-objects/ref-organ/united-female/v1.5/assets/3d-vh-f-united.glb
- License: https://creativecommons.org/licenses/by/4.0/

Adaptations: translated native meter/Y-up coordinates onto the stage, coincident vertices welded and source normals averaged, geometry simplified with a 0.2% per-structure relative error bound, and normals quantized. Colors and display systems are curated for this interface. All 888 source meshes are represented, with 1,073 source nodes available as selectable individual or compound concepts.

This is a reference assembly with whole-body surface and selected organs, including female reproductive anatomy. Its skeleton and muscle coverage is partial. It is not a complete model of every human structure or a single-person scan. Eight placenta/umbilical structures are classified under Pregnancy reference and hidden by default.

## Local adaptations

### TCIA Healthy Total Body CTs, subject 003

Published segmentations and clinical metadata: TCIA Healthy-Total-Body-CTs
collection contributors, https://doi.org/10.7937/NC7Z-4F76, CC BY 4.0.
Official source and licence evidence:
https://www.cancerimagingarchive.net/collection/healthy-total-body-cts/.
Subject 003 is female, age 26, as recorded in clinical release v02 20240927.
Only the public segmentation labelmap and metadata were downloaded; CT images
were not downloaded. The published segmentations were generated using MOOSE.

Adaptations: scikit-image marching cubes, NIfTI affine converted from RAS mm to
viewer left/up/anterior metres, translation to a ground plane, derived normals,
meshoptimizer simplification at 0.2% relative error, binary packing and gzip.
All 36 present labels are retained. Diffuse muscle and fat use marching-cubes
step size 3 voxels; other labels use step size 1. Labels often group both sides,
multiple bones or entire tissues. They must not be counted as individual organs
or presented as manually validated anatomy. Registration to VHF is pending.

### Denver Visible Human Female 2022, Final 3D STL Models

Andreassen, T. E., Hume, D. R., Hamilton, L. D., Walker, K. E., Higinbotham, S. E.
& Shelburne, K. B. (2022). *Three-dimensional lower extremity musculoskeletal
geometry of the Visible Human Female and Male.* Scientific Data.
https://doi.org/10.1038/s41597-022-01905-2. Overclosure processing: Andreassen et
al. (2022), https://doi.org/10.48550/arXiv.2209.06948. Dataset record:
https://digitalcommons.du.edu/visiblehuman/1/ (DOI 10.56902/COB.vh.2022.1),
University of Denver Center for Orthopaedic Biomechanics. CC BY 4.0, as stated in
the archive README. Supported by NIH grant U01 AR072989.

Source donor: NLM Visible Human Female cryosections. The final models are manual
segmentations after smoothing and overclosure correction by the authors.

Adaptations: STL vertices welded, source millimetre axes (x right, y anterior,
z superior) permuted to viewer left/up/anterior metres, translated to a ground plane
and centred, derived vertex normals, meshoptimizer simplification at 0.2% relative
error, binary packing and gzip. All 128 meshes are retained with their archive member
name, CRC and SHA-256. Display names normalize four source spellings and two
side-inconsistent labels; the original labels remain in each provenance record. No
other donor is combined with this geometry in the Denver view.

### Application changes

The Female Open Human Atlas fork adds per-mesh source records, SHA-256 identities,
an imported concept catalog, coverage reports and a provenance inspector. Source
binary geometry is unchanged. Display coordinates are not an anatomical registration
to VHF. Component donor identity and confidence remain explicitly unassessed.
Application code remains MIT; dataset licences remain attached to their sources.

Experimental composition additionally applies a similarity transform fitted to six
organ bounding-box centres for the torso, a second similarity transform fitted to six
grouped-bone bounding-box centres for the Denver VHF lower limb, and a separate brain
bounding-box fit for cranial structures. Matrices, scale changes and residuals are in `transforms/`
and `generated/registration-report.json`. These are unreviewed cross-donor display
adaptations, not measurements of one person or validated anatomical registration.

### NLM Visible Human Female fresh CT and TotalSegmentator labels

Image data: U.S. National Library of Medicine, The Visible Human Project, Visible Human
Female data set (1995), radiological/normalCT (fresh CT, 22 September 1993 per headers).
"Courtesy of the U.S. National Library of Medicine." Downloaded from
https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/ under the NLM Terms
and Conditions (https://www.nlm.nih.gov/databases/download/terms_and_conditions.html).
NLM does not endorse this atlas. The derived label maps and meshes are not NLM data and do
not reflect the current NLM data; they were produced here.

Segmentation: Wasserthal, J. et al. (2023). TotalSegmentator: Robust Segmentation of 104
Anatomic Structures in CT Images. Radiology: Artificial Intelligence.
https://doi.org/10.1148/ryai.230024. TotalSegmentator 2.18.0, task `total` (Apache-2.0),
CPU inference; licensed subtasks were not used.

Adaptations: 1,734 GE slices decompressed, converted to Hounsfield units, resampled onto a
480 mm field of view and stacked at 1 mm in file order (two exams, junction recorded);
marching cubes per label (step 2 voxels above 400 cm3); rigid same-donor registration of the
CT pelvis onto the Denver hip bones and sacrum (`transforms/nlm-ct-to-vhf.json`); axis and
unit conversion to the viewer stage; meshoptimizer simplification at 0.2% relative error;
binary packing and gzip. Labels are automatic model output and are not anatomically
reviewed. All present labels are retained.

### Ontology terms

UBERON and FMA labels, synonyms and cross-references were retrieved from the EBI Ontology
Lookup Service (https://www.ebi.ac.uk/ols4/) and stored in
`registry/ontology-crosswalk-reviewed.json`. UBERON is CC BY 3.0; FMA is CC BY 3.0
(Structural Informatics Group, University of Washington).
