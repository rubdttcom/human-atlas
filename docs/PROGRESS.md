# Implementation status

This is an incomplete implementation of `female-open-human-atlas-plan.md`.
The full objective remains active. Do not interpret working rendering or licence
checks as validation of a complete anatomical atlas.

## Authoritative state

- Local fork: `ashemag/human-atlas`, base `7a383d3ee2759e3ddf157c704fb8814fd0c50bcb`, branch `female-open-atlas`.
- HRA Female v1.5: 888 meshes restored from `d72b4f6db42e41a8db84b1c19ff6d86ee7b65284`. Reference assembly, individual donors unresolved.
- BodyParts3D 4.0: 2,234 male reference meshes, selectable separately. Not used in the female composition.
- TCIA Healthy Total Body CTs: subject 003, female, 26 years. Clinical file v02 20240927 verifies the donor. All 36 present segmentation labels were converted; 1,049,570 optimized triangles, about 7.3 MB gzip. Some labels contain many bones or bilateral organs. Masks are automatic and unreviewed.
- Experimental composition 0.2: 938 meshes. TCIA trunk/upper-limb skeleton, HRA organ detail, TCIA endocrine/psoas/tissue coverage, and the full Denver VHF lower limb (128 meshes) replacing eight grouped TCIA lower-limb bone labels (femur, fibula, patella, pelvis, tarsal, metatarsal, toes, tibia) and four HRA thigh muscles/tendons. Torso similarity fit of six organ proxies, RMS 27.21 mm, maximum 35.40 mm. Denver lower limb similarity fit of six grouped-bone proxies, RMS 28.13 mm, maximum 40.91 mm (patella), scale 0.981. Cranial structures use a separate brain-bounds fit. No validated canonical VHF registration. Overrides are configurable per source mesh.
- BMFToolkit: downloaded and inspected at `e3e781ef166162438273cc1853d6f318482fea67`; 63 meshes, 31 segmented right-side bones and 32 mirrored/symmetrized meshes. Not shipped while exact data licence scope remains unresolved. Zlib software terms and Zenodo `other-open` metadata are recorded evidence, not proof of a CC licence for data.
- Denver VHF 2022 (`digitalcommons.du.edu/visiblehuman/1`): CC BY 4.0 verified in the archive README. The endpoint sits behind a Cloudflare JavaScript challenge, so plain HTTP clients receive HTTP 403; `scripts/fetch-denver.py` downloads through a local Chrome session and records URL, size and SHA-256. Imported: all 128 final STL meshes (28 bones incl. midline sacrum and coccyx, 76 muscles, 16 cartilages, 8 ligaments), 2,335,390 source triangles, 536,060 after optimization, about 7.7 MB gzip. Frame verified empirically (x right, y anterior, z superior, mm; femur extent 417 mm) and converted to the viewer stage by axis permutation and unit scale only. Sides use inconsistent file labels for four structures; display names are normalized and the source label is preserved per mesh. Not manually reviewed here; final surfaces are smoothed and overclosure-corrected by the source.

## Plan audit

| Phase | Evidence | Remaining work |
| --- | --- | --- |
| 0 Survey | `datasets.csv`, 14 candidate sources | Finish primary-source checks for every candidate and exact asset/release licences. |
| 1 Ontology | `structures.csv`, `registry/ontology-crosswalk.json` | Full UBERON/FMA/TA2 universe and reviewed equivalences. Current catalog is only the imported source union. |
| 2 Coverage | `coverage.csv`, `generated/coverage-matrix.json`, interactive coverage table | Register candidate availability outside imported data; distinguish complete compound coverage from partial coverage. |
| 3 VHF base | Denver VHF lower-limb import (128 meshes, native aligned VHF image frame), HRA import, BMFToolkit inventory | Trunk, upper limb and head remain without donor-coherent VHF geometry. Define the canonical VHF space from the Denver/NLM image frame and register other sources into it; verify the coordinate chain against NLM image metadata. |
| 4 CT scaffold | Downloaded subject 003 segmentation, reproducible extraction and QA | Review masks, label mapping and anatomical outliers. No new CT inference has run. |
| 5 Specialized | Candidate inventory | OpenEar, SPIDER, SPARC, Teeth3DS+, HiP-CT imports and specialist LODs. |
| 6 Fallback | BodyParts3D separate comparison reference | Audit and ingest Z-Anatomy/Open3Dmodel as needed; register fallbacks explicitly. |
| 7 QA | Binary/provenance/composition tests, geometry measurements (all 128 Denver meshes watertight after welding), licence checks | Anatomical review, self-intersections, registration landmarks, surface distance and local distortion. |
| 8 Web atlas | Original React/Three.js viewer, five source modes (HRA, TCIA, Denver VHF, composite, BodyParts3D), provenance export, coverage navigation with a measured-female filter | Donor filters, source alternatives comparison, registration review controls, multiresolution overlays. |

## Known limitations

- The atlas has no validated VHF canonical space. TCIA is a provisional display frame. Denver meshes are shown in their native aligned VHF image frame, which is the natural candidate for the canonical space, but nothing else is registered to it yet.
- A 27 mm landmark-proxy residual is not sufficient evidence of anatomical alignment. The composite remains explicitly experimental.
- CT tissue depots contain nonmanifold edges. They are preserved as optional tissue maps, not silently repaired or counted as individual muscles.
- `Toes` has small outlying geometry extending above the head. This is present in the source segmentation and requires review; a plausible body silhouette does not prove mask correctness.
- HRA source hierarchy can include compound regions; mesh and concept counts must remain separate.
- Source-local TCIA and Denver labels are not assigned guessed UBERON IDs. Denver bones therefore do not merge with HRA/TCIA skeleton entries in the coverage matrix until a reviewed crosswalk exists.
- Denver's female final STL archive contains no fat geometry; the paper's per-subject counts include the male dataset.
- The imported catalog's `no-direct-geometry` entries include hierarchy concepts. They are not a count of all missing human anatomy.
- Upstream npm installation reports 11 vulnerabilities. Dependency remediation has not yet been evaluated.

## Next work

Order and acceptance criteria are in `docs/female-open-human-atlas-plan.md`, section 29.

1. Make the VHF image frame the canonical female space: register TCIA 003 and HRA into it (invert the current fits), replace bounding-box proxies with manually marked bone landmarks, add bone-to-bone surface distances, target RMS < 15 mm in the lower limb.
2. Reviewed UBERON/FMA crosswalk for Denver (128) and TCIA (36) labels; then merge Denver bones with HRA/TCIA skeleton entries in coverage and recompute KPIs.
3. Verify NLM VHF terms and segment the VHF CT (TotalSegmentator/MOOSE) for trunk, upper limb and head in the same donor and frame as Denver.
4. Resolve BMFToolkit data terms; if CC, compare bone by bone with Denver in the VHF frame.
5. Anatomical review and QA (self-intersections, cervical continuity, outliers such as TCIA `Toes`).
6. Specialist datasets (OpenEar, SPIDER, Teeth3DS+, SPARC, HiP-CT), UI best-available/donor/compare modes, then fallback audits.

All large input data are outside Git under `data/raw/` or `sources/`. Nothing has
been published, deployed externally, or represented as anatomically validated.
