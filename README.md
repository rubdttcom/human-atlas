# Female Open Human Atlas

Local fork of [ashemag/human-atlas](https://github.com/ashemag/human-atlas), combining
open anatomical sources with a source record for every mesh. The original
React/Three.js renderer, search, system layers, isolation and exploded views are
retained. New controls expose source/donor evidence, licences, transforms, geometry
checks and an interactive coverage table.

**Work in progress. The atlas is not anatomically validated or complete.**

| View | Included geometry | Interpretation |
| --- | --- | --- |
| HRA Female v1.5 | 888 source meshes | Female reference assembly; per-component donors unresolved. |
| TCIA female 003 | 36 published CT segmentation labels | Female donor, 26 years; automatic and unreviewed; many labels group structures. |
| Denver VHF lower limb | 128 final STL meshes | Female donor VHF, manual cryosection segmentation, pelvis to toes: bones, muscles, cartilage, ligaments. Native aligned VHF image frame. Smoothed and overclosure-corrected by the source; not reviewed here. |
| Experimental composition | 938 selected meshes | Denver VHF lower limb (bones, muscles, cartilage, ligaments), TCIA trunk skeleton, HRA detailed organs, additional CT structures. Torso fit RMS 27.2 mm; lower-limb fit RMS 28.1 mm; separate provisional head fit. |
| BodyParts3D 4.0 | 2,234 source meshes | Male reference for comparison, not included in the female composition. |

The 4,316 catalog entries are the imported source union, not a complete anatomical
ontology. Current reports separately identify 128 measured-female entries (Denver
VHF), 717 female-reference entries, 36 female CT labels awaiting review, and 1,589
template-only entries. Hierarchy-only
entries without direct meshes must not be confused with missing human anatomy.

## Run

```bash
npm ci
npm run dev -- --port 3017
```

Open http://localhost:3017. The source selector switches reference frames; the
experimental composition also has a direct URL:
http://localhost:3017/?source=composed.

## Data and checks

- [Implementation status and remaining work](docs/PROGRESS.md)
- [Full original plan](docs/female-open-human-atlas-plan.md)
- [Reproducible download, conversion and verification](docs/REPRODUCIBILITY.md)
- [Dataset inventory](datasets.csv), [structure catalog](structures.csv), [coverage](coverage.csv)
- [Source records](registry/sources.json), [donors](registry/donors.json), [licences](registry/licences.json)
- [Registration evidence](generated/registration-report.json), [geometry QA](generated/qa-report.json)
- [Attribution](public/ATTRIBUTION.md), [original upstream README](docs/UPSTREAM-README.md)

The source binary buffers retain their original geometry identity. Every record
includes source asset, source revision or input hash, chunk SHA-256, donor evidence,
geometry type, applied display transform, licence and review status. Confidence is
unassessed unless evidence establishes it. An experimental alignment is not a VHF
canonical registration.

```bash
npm run check
python3 scripts/validate-provenance.py
.venv/bin/python scripts/validate-composition.py
./atlas check-licenses --target open-clean
npm run build
```

Input volumes and external source repositories are excluded from Git. Denver VHF
trunk/upper-limb coverage does not exist (the dataset is pelvis to toes); additional
female donors, specialist datasets, reviewed ontology bridges and a validated VHF
canonical space remain unfinished. Denver assets need `scripts/fetch-denver.py`
(local Chrome) because the publisher's endpoint rejects plain HTTP clients. BMFToolkit's 63 meshes are
inventoried locally, with mirrored anatomy distinguished from segmented anatomy;
they are not part of the public build.

Application code: MIT. Included data: CC BY 4.0 with separate source attribution.
