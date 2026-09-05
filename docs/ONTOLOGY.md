# Ontology status

The current catalog is the union of imported HRA terms, BodyParts3D FMA concepts,
and local TCIA label IDs. `FMA123` is normalized to `FMA:123`; explicit name-side
information is retained separately and in canonical keys where available.

No UBERON/FMA equivalence is inferred from similar names. No TA2 mapping has been
imported. TCIA's grouped labels stay source-local until their anatomical extent can
be mapped without implying individual bones or unilateral organs.

`source-hierarchy-concept` entries can lack a direct mesh while referencing meshes
through their source hierarchy. The coverage report says `no-direct-geometry`,
not that these structures are absent from all anatomical datasets.

Canonical VHF space, full ontology import and reviewed cross-source equivalences
remain required work. The current 4,113 entries must not be advertised as the full
human anatomical universe.
