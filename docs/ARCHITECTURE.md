# Architecture

The local fork retains the upstream batched Three.js renderer and binary geometry
layout. Original source atlases live in `public/models/`; their manifests are not
rewritten to imply a female donor or canonical registration.

Sources and frames:

| Source | Frame in its own view | Path into `VHF-image-2022` |
| --- | --- | --- |
| Denver VHF | aligned VHF image frame (defines the canonical space) | identity |
| NLM VHF CT labels | canonical stage already (voxel -> CT RAS -> `nlm-ct-to-vhf` -> stage) | rigid same-donor pelvis registration, scale 1 |
| HRA female | HRA viewer stage | similarity on organ bounding-box proxies onto the CT organs; head by bounding-box fit into the CT brain |
| TCIA 003 | TCIA viewer stage | similarity on ten automatic pelvic landmarks (alternative source, not composed) |
| BodyParts3D | BodyParts3D stage | none (male template, comparison only) |

`scripts/build-registry.py` reads the actual manifests and source metadata, resolves
dataset-local labels through the reviewed crosswalk (`registry/ontology-crosswalk-reviewed.json`),
hashes every source chunk, and generates provenance-enriched source atlases, catalog tables
and the coverage matrix (individual, grouped and partial coverage kinds; per-source candidates).
`scripts/extract-landmarks.py` derives bone landmarks by explicit rules;
`scripts/register-nlm-ct.py` registers the same-donor CT to Denver and verifies the frame;
`scripts/compose-female.py` writes the experimental composition with its explicit transforms,
proxy fits, surface-distance evidence and selection recipe. `scripts/qa-geometry.py` and
`scripts/qa-anatomy.py` measure geometry; `registry/review-status.json` holds human decisions.

The UI loads one atlas at a time (HRA, TCIA, Denver VHF, NLM VHF CT, composite, BodyParts3D).
Source selection uses separate coordinate frames; the Denver and NLM CT views are already the
canonical frame. Only the composite applies the recorded cross-donor transforms. Every selected
mesh retains its source identity and downloadable provenance record. The composite exposes a
donor filter, a registration review panel (landmark pairs drawn in the scene, per-landmark
decisions exported as `landmark-review.json`), a side-by-side source comparison for structures
with alternatives, and coverage filters for multi-source and partial (grouped label) entries.

`data/raw/`, `data/derived/` and `sources/` hold excluded large input and intermediate files.
Generated published geometry is licensed per source. `docs/PROGRESS.md` records unfinished
requirements; the presence of a pipeline component is not evidence that its anatomical scope
is complete.
