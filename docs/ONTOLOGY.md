# Ontology status

The catalog is the union of imported terms. HRA and BodyParts3D FMA/UBERON identifiers are kept; `FMA123` is normalized to `FMA:123`.
Dataset-local labels (Denver VHF, TCIA 003, NLM VHF CT) and lateralized FMA identifiers (HRA, BodyParts3D) resolve to UBERON/FMA through
`registry/ontology-crosswalk-reviewed.json`, built by `scripts/build-crosswalk.py` from curated proposals (`registry/crosswalk-proposals.json`)
and the EBI Ontology Lookup Service: every entry stores the OLS record (IRI, label, synonyms, cross-references, definition), the match type
(exact label, exact synonym, FMA parent with UBERON cross-reference) and a review status. Nothing is applied without a retrievable term.

Crosswalk summary (2026-09-05T20:28:39Z): denver-vhf: 69 of 69 applied (54 UBERON, 15 FMA only); tcia: 35 of 36 applied (36 UBERON, 0 FMA only); nlm-vhf-ct: 114 of 117 applied (114 UBERON, 0 FMA only); hra-female: 176 of 201 applied (120 UBERON, 56 FMA only); bodyparts3d: 1221 of 1360 applied (777 UBERON, 444 FMA only).
Unresolved or uncertain: 168 entries (listed in the file); they keep their source identifiers.

Laterality is explicit in canonical keys (`UBERON:0000981|left`). Grouped CT labels (both sides in one mesh) are catalog entries of their own and
appear as `grouped_candidates` (partial coverage) on the lateral entries. Anatomist review of every equivalence is pending; no TA2 mapping has been imported.

`source-hierarchy-concept` entries can lack a direct mesh while referencing meshes through their source hierarchy. The coverage report says `no-direct-geometry`,
not that these structures are absent from all anatomical datasets. The catalog must not be advertised as the full human anatomical universe.
