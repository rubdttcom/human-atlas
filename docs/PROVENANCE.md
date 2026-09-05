# Structure provenance

Source mesh records include dataset, source asset, source revision/input identity,
chunk SHA-256, original ontology term and its reviewed crosswalk resolution, donor,
donor sex, reference sex, geometry category and granularity, licence, transform chain
and confidence/review state.

HRA reference sex is female; individual component donor sex is unresolved. BodyParts3D
is a male reference. TCIA subject 003 is verified female from the corrected clinical
spreadsheet. Denver meshes come from the single female VHF donor and keep archive member,
CRC and STL hash; their frame is the aligned VHF image frame, which defines canonical
space `VHF-image-2022` (`transforms/canonical-space.json`), so Denver source records carry
`canonical_space: VHF-image-2022` with an identity transform. The NLM VHF CT records come
from the same donor: they keep the CT volume hash, the TotalSegmentator label map hash,
the label value and model, and the rigid pelvis registration `nlm-ct-to-vhf` (rotation about
2 degrees, scale 1, pelvis p95 a few millimetres) that places them in the canonical space;
their `geometry_type` is `automatic_segmentation` and their anatomy is unreviewed.
BMFToolkit distinguishes right segmentations from mirrored left anatomy and a symmetrized
sacrum; it is compared, not shipped.

HRA, BodyParts3D and TCIA source records have no VHF registration in their own views.
Composite records identify the transform into `VHF-image-2022` (`nlm-stage-to-vhf`,
`hra-stage-to-vhf`, `hra-head-to-vhf`; `tcia003-stage-to-vhf` for the alternative TCIA
source), its RMS or p95, and `review_status: unreviewed`, and separately retain the
original source chunk hash. Landmarks are automatic geometric rules recorded in
`transforms/landmarks/` with `manual_review: pending`; organ proxies are bounding-box
centres. Derived chunk hashes identify the transformed output.

Ontology mapping is recorded per mesh (`ontology_mapping`): either the inherited source
identifier or the reviewed crosswalk entry with its OLS match type. Geometry checks
(boundary edges, nonmanifold edges, self-intersecting triangle pairs, connected components,
outlier components) are measurements, not anatomical validation. Confidence remains null.
No numeric confidence has been invented from a visually plausible rendering or from a
successful file-integrity check.
