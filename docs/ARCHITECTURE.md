# Architecture

The local fork retains the upstream batched Three.js renderer and binary geometry
layout. Original source atlases live in `public/models/`; their manifests are not
rewritten to imply a female donor or canonical registration.

`scripts/build-registry.py` reads actual manifests and source metadata, normalizes
identifier syntax, hashes every source chunk, and generates provenance-enriched
source atlases, catalog tables and coverage. `scripts/compose-female.py` writes a
separate experimental composition and its explicit transforms/selection recipe.

The UI loads one atlas at a time (HRA, TCIA, Denver VHF, composite, BodyParts3D).
Source selection uses separate coordinate frames.
Only the composite applies the recorded cross-donor transforms. Every selected
mesh retains its source identity and downloadable provenance record.

`data/raw/` and `sources/` hold excluded large input files. Generated published
geometry is licensed per source. `docs/PROGRESS.md` records unfinished requirements;
the presence of a pipeline component is not evidence that its anatomical scope is complete.
