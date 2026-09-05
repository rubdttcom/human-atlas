# Imported-source coverage

| Metric | Count |
| --- | ---: |
| canonical_catalog_entries | 4263 |
| source_meshes | 3400 |
| female_measured | 128 |
| registered_female | 231 |
| female_ct_same_donor | 114 |
| female_segmented_unreviewed | 139 |
| female_reference | 717 |
| template_only | 1461 |
| without_direct_geometry | 1880 |
| multi_source_entries | 248 |
| denver_hra_merged_entries | 22 |
| crosswalk_applied_meshes | 1712 |

Counts describe the imported source union, not all human anatomy. Hierarchy concepts without direct geometry are included.
CT labels may group many structures; HRA assembly sex does not establish each component donor sex.
`female_ct_same_donor` counts entries covered by the NLM VHF CT labels (same donor as Denver, automatic segmentation).

- Catalog is the imported source union, not the complete human ontology.
- Dataset-local Denver and TCIA labels and lateralized HRA FMA identifiers resolve to UBERON/FMA through registry/ontology-crosswalk-reviewed.json (OLS evidence per term; anatomist review pending). No TA2 crosswalk imported.
- Grouped CT labels (both sides in one mesh) are listed as partial coverage of each lateral entry, not as individual structures.
- Canonical space VHF-image-2022 is the Denver aligned image frame, verified against the NLM CT headers (rigid pelvis fit: rotation about 2 deg, scale 1.00). Denver meshes are native; NLM CT labels of the same donor are placed by that rigid fit (registered_female). TCIA 003 and HRA are registered experimentally in the composite only, without anatomical QA.
- Best available ranks source evidence but does not authorize spatial composition.
