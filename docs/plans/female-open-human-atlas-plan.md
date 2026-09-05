# Plan: an open, composite and traceable female anatomical atlas

> **Goal:** build the most complete open 3D female anatomical atlas possible by combining several datasets, without pretending that geometry from different donors is one real person.  
> **Guiding principle:** *best source per structure*, with provenance, licence, sex/donor, registration method and confidence level stored per structure.

**Document status:** 5 September 2026. Execution status and next steps are in section 29 (at the end).

---

## 1. Starting point

The project [`ashemag/human-atlas`](https://github.com/ashemag/human-atlas) is a 3D web viewer currently based on **BodyParts3D 4.0**, with:

- 2,234 selectable OBJ meshes;
- 3,432 FMA concepts in the hierarchy;
- adult male reference anatomy;
- React + Three.js as the rendering layer;
- geometry simplified and packed for the browser.

The repository itself previously had a female version based on **Human Reference Atlas / HuBMAP Female v1.5**, with:

- 888 meshes;
- 1,073 nodes/concepts;
- body surface;
- selected organs;
- female reproductive anatomy;
- partial muscle and skeleton coverage.

References:

- Human Atlas: https://github.com/ashemag/human-atlas
- Attribution: https://github.com/ashemag/human-atlas/blob/main/public/ATTRIBUTION.md
- HRA Female v1.5: https://lod.humanatlas.io/ref-organ/united-female/v1.5
- HRA Female GLB: https://cdn.humanatlas.io/digital-objects/ref-organ/united-female/v1.5/assets/3d-vh-f-united.glb
- DOI HRA Female v1.5: https://doi.org/10.48539/HBM352.BTSQ.586

The real limitation is not that "no open female models exist", but that **there is no single female equivalent of BodyParts3D with the same coverage, granularity and consistency**.

---

## 2. Goal of the new project

Do not look for a single winning dataset.

Build a **composite atlas**:

```text
Female Open Human Atlas
│
├── canonical female anatomical space
│
├── primary geometry from the same donor where possible
│
├── registered geometry from other donors
│
├── specialised high-resolution overlays
│
├── templates used only as fallback
│
└── provenance + licence + confidence per structure
```

For any structure the atlas must be able to answer:

- what does it represent?
- which dataset does it come from?
- which donor does it come from?
- donor sex?
- is the geometry measured, segmented, registered or inferred?
- which transform has been applied?
- which licence does it have?
- how confident are we in that representation?
- which alternative sources exist for the same structure?

---

# 3. Important precedent: Open Twin XR

[`Opening-Science/open-twin-xr`](https://github.com/Opening-Science/open-twin-xr) is developing a very similar strategy:

- several registered anatomical atlases;
- several donors;
- "best per system" composition;
- visible provenance;
- separation between atlas and overlays;
- absence represented as "no data" instead of invented information;
- mapping of structures to ontologies;
- licence audit;
- publishable build that can exclude problematic assets;
- full female body from a TCIA CT;
- BodyParts3D, Z-Anatomy, HRA, Visible Human, OpenEar and other sources.

References:

- Repo: https://github.com/Opening-Science/open-twin-xr
- Model pipeline: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/MODEL_PIPELINE.md
- Ontology map: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/ONTOLOGY_MAP.md
- Licence log: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/LICENCE_LOG.md
- Resources: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/RESOURCES.md
- Licence registry: https://github.com/Opening-Science/open-twin-xr/blob/main/licences.json

**Recommendation:** do not reinvent their ingestion, registration, provenance and licence work. Use it as an architectural reference and even evaluate reusing parts of their pipeline.

---

# 4. Canonical anatomical space

## 4.1 Proposal

Use the **Visible Human Female (VHF)** as the main female reference space **where possible**.

Reasons:

- complete female body with cryosections;
- CT;
- MRI;
- high resolution;
- independent derived datasets exist;
- allows new segmentations where no published mesh exists.

NLM Visible Human Project:

- Home page: https://www.nlm.nih.gov/research/visible/visible_human.html
- Data access: https://www.nlm.nih.gov/research/visible/getting_data.html
- Female data: https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/index.html

### Important

Do not assume that every model labelled "HRA Female" is geometry segmented directly from one woman.

HRA is a **reference assembly**, and `human-atlas` itself warns that its historical female model:

> is not a complete scan of a single person.

Therefore:

```text
VHF imaging / derived VHF geometry
    = donor-coherent primary geometry

HRA female reference organs
    = registered reference geometry

other female datasets
    = registered donor geometry

male / generic atlases
    = template fallback only
```

---

# 5. Candidate sources

## 5.1 BodyParts3D

### Provides

- thousands of anatomical structures;
- strong general coverage;
- FMA identifiers;
- excellent source for building the ontology/manifest;
- useful as geometric fallback.

### Limitation

- a single male model;
- must not be presented as measured female anatomy.

### Use

- ontology and nomenclature;
- anatomical reference;
- last geometric fallback;
- male/female comparison.

References:

- Official archive: https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html
- Current licence: https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html
- Paper: https://doi.org/10.1093/nar/gkn613
- Mirror / tooling: https://github.com/Kevin-Mattheus-Moerman/BodyParts3D
- API / modern 4.x set: https://github.com/olivercase/body_parts_3d_api

> Licence note: historical copies of BodyParts3D keep CC BY-SA 2.1 Japan text, while the current official archive and `human-atlas` state CC BY 4.0. The licence must be verified against the exact version of the assets used.

---

## 5.2 Human Reference Atlas / HuBMAP

### Provides

- male and female models;
- reference organs;
- female reproductive system;
- modern terminology;
- UBERON and semantic knowledge;
- CCF / Common Coordinate Framework;
- APIs and knowledge graph.

### Use

- female organs;
- ontology;
- coordinate system / registration;
- semantic crosswalk;
- spatial reference.

References:

- HRA portal: https://humanatlas.io
- 3D Reference Library: https://humanatlas.io/3d-reference-library
- HRA UI: https://github.com/hubmapconsortium/hra-ui
- HRA registrations: https://github.com/hubmapconsortium/hra-registrations
- HRA API: https://apps.humanatlas.io/hra-api/
- HuBMAP APIs: https://docs.hubmapconsortium.org/apis.html
- HRA VCCF: https://github.com/hubmapconsortium/hra-vccf
- HRA-AMAP: https://github.com/cns-iu/hra-amap
- Female v1.5: https://lod.humanatlas.io/ref-organ/united-female/v1.5

---

## 5.3 Visible Human Female — NLM

### Provides

- cryosections;
- CT;
- MRI;
- complete body;
- the possibility of segmenting structures that no atlas has published as a mesh.

### Use

It must be the **main female volumetric ground truth** whenever the licence and the structure's resolution allow it.

References:

- https://www.nlm.nih.gov/research/visible/visible_human.html
- https://www.nlm.nih.gov/research/visible/getting_data.html
- https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/index.html

---

## 5.4 University of Denver — Visible Human Female Lower Extremity

### Provides

Musculoskeletal geometry derived directly from the Visible Human Female:

- muscles;
- bones;
- cartilage;
- ligaments;
- fat;
- pelvis → ankle;
- original STL;
- smoothed STL;
- final models;
- segmentation masks.

The male + female set contains 260 geometries and, per subject:

- 76 muscles;
- 28 bones;
- 16 cartilages;
- 8 ligaments;
- 2 fat geometries.

### Use

**Primary source for the female lower limb**, with a major advantage: it derives from the same Visible Human Female that we can use as volumetric reference.

References:

- Dataset: https://digitalcommons.du.edu/visiblehuman/
- Paper: https://doi.org/10.1038/s41597-022-01905-2
- Dataset DOI: https://doi.org/10.56902/COB.vh.2022.0
- FEMORS tools: https://github.com/thor-andreassen/femors

---

## 5.5 BMFToolkit

### Provides

High-resolution meshes of the lower-body bones of an adult woman, derived from CT of the Visible Human dataset.

Includes tools to:

- visualise;
- resample;
- modify;
- scale the meshes;
- landmarks;
- joint axes.

### Use

Complement/validation for:

- pelvis;
- leg;
- foot;
- VHF bone geometry.

References:

- Repo: https://github.com/manishsreenivasa/BMFToolkit
- Paper: https://arxiv.org/abs/1804.03655

---

## 5.6 Healthy Total Body CTs — TCIA

### Provides

30 healthy adults with whole-body CT.

Includes:

- sex;
- height;
- weight;
- BMI;
- CT;
- segmentations;
- 37 tissue classes;
- 13 abdominal organs;
- 20 bones;
- subcutaneous fat;
- visceral fat;
- skeletal muscle;
- psoas.

Open Twin XR already uses a **female subject** from this set as a complete female body.

### Use

- complete female scaffold;
- filling regions without published VHF geometry;
- base for running modern segmenters;
- inter-donor validation.

References:

- TCIA: https://www.cancerimagingarchive.net/collection/healthy-total-body-cts/
- DOI: https://doi.org/10.7937/NC7Z-4F76

### Licence

- segmentations: CC BY 4.0;
- clinical data: CC BY 4.0;
- CT images: subject to the TCIA/NIH access conditions stated by the collection.

Do not assume that the whole volume can be redistributed with the atlas.

---

## 5.7 CADS

### Provides

CT segmentation model/dataset with a target space of about **167 structures**.

Can help produce:

- larynx;
- orbital structures;
- cochlea;
- spine;
- spinal cord;
- individual ribs;
- other structures hard to obtain from general atlases.

### Use

Not necessarily as a mesh source.

Main use:

```text
female CT
    ↓
CADS
    ↓
labelmap
    ↓
mesh
    ↓
QA
```

References:

- Repo/releases: https://github.com/murong-xu/CADS/releases

### Licence

CADS publishes different weight variants under different conditions. The research model is announced under CC BY-NC-SA 4.0; other weights add specific conditions from training datasets.

Must be audited **per release/model**.

---

## 5.8 SPIDER

### Provides

Lumbar MRI dataset:

- 447 series;
- 218 patients;
- vertebrae;
- intervertebral discs;
- spinal canal;
- supervised manual segmentations.

### Use

- lumbar spine;
- validation;
- disc geometry;
- spinal canal.

References:

- Repo: https://github.com/cdoswald/SPIDER
- Paper: https://doi.org/10.1038/s41597-024-03090-w
- arXiv: https://arxiv.org/abs/2306.12217
- Challenge: https://spider.grand-challenge.org/

Licence of the published dataset: **CC BY 4.0**.

---

## 5.9 OpenEar

### Provides

Eight 3D models of the human temporal bone based on:

- CBCT;
- micro-slicing;
- colour data;
- external/middle/inner ear;
- cochlea;
- vestibule;
- ossicles;
- tympanic membrane;
- associated neurovascular structures.

### Use

**Specialised overlay**, not base geometry of the female skull.

It must keep its real size/donor and must not be silently deformed to pretend it belongs to the canonical donor.

References:

- Zenodo: https://zenodo.org/records/1473724
- Alternative record: https://zenodo.org/records/1342658

---

## 5.10 SPARC whole-body scaffold — Pennsieve Dataset 307

### Provides

Integrated 3D human model with:

- organs;
- musculoskeletal system;
- vasculature;
- nervous system;
- nerve centrelines.

### Use

Very interesting as a **topological scaffold for nerves and vessels**, even when the final visual geometry comes from other sources.

References:

- Dataset: https://discover.pennsieve.io/datasets/307
- DOI: https://doi.org/10.26275/BBVG-GJ86

Licence: **CC BY 4.0**.

---

## 5.11 Human Organ Atlas / HiP-CT

### Provides

Multiscale 3D imaging of real human organs.

Approximate resolutions:

- whole organ: ~20 µm/voxel;
- local regions: down to ~1 µm/voxel.

### Use

Not as a complete body.

Yes as:

- high-resolution overlay;
- internal organ detail;
- microscopic level;
- source for specialised segmentations.

Architecture:

```text
LOD 0  body
  ↓
LOD 1  organ
  ↓
LOD 2  substructure
  ↓
LOD 3  tissue / microanatomy
```

References:

- Portal: https://human-organ-atlas.esrf.eu
- ESRF: https://www.esrf.fr/home/news/general/content-news/general/3d-atlas-of-human-organs-made-available-online.html
- UCL HiP-CT: https://mecheng.ucl.ac.uk/hip-ct/
- Databases: https://mecheng.ucl.ac.uk/hip-ct/presentation/
- Paper: https://pmc.ncbi.nlm.nih.gov/articles/PMC12978218/

---

## 5.12 Teeth3DS+

### Provides

Large dataset of 3D intraoral scans:

- at least 1,800 scans;
- 900 patients;
- upper and lower jaw;
- 23,999 annotated teeth;
- per-vertex labels;
- FDI identification.

### Use

- dentition;
- dental atlas;
- morphological diversity;
- source for selecting/reconstructing reference teeth;
- validation of dental anatomy.

It does not by itself represent the complete skull/maxilla.

References:

- Web: https://crns-smartvision.github.io/teeth3ds/
- Dataset: https://osf.io/xctdy/
- Paper: https://arxiv.org/abs/2210.06094
- Challenge: https://github.com/abenhamadou/3dteethseg22_challenge

---

## 5.13 Z-Anatomy

### Provides

High-coverage anatomical atlas:

- musculoskeletal;
- nervous system;
- cardiovascular;
- lymphatic;
- viscera;
- surface regions;
- many structures that may be missing from female datasets.

### Fundamental limitation

Its main human model is male and derives partly from BodyParts3D.

### Use

**Template/fallback**, not a primary female source.

```text
female structure available
    → use it

not available
    → look for another female dataset

not available
    → generic human template

last fallback
    → registered Z-Anatomy / BodyParts3D
```

References:

- Organisation: https://github.com/Z-Anatomy
- Human models: https://github.com/Z-Anatomy/Models-of-human-anatomy
- Historical app: https://github.com/LluisV/Z-Anatomy

### Licences

Although the aggregate repository declares CC BY-SA 4.0, it contains or references third-party components with different licences, including some NC.

**Per-structure audit is mandatory.**

---

## 5.14 AnatomyTOOL / Open3Dmodel

### Provides

Another source of reusable anatomical geometry, potentially compatible as a template.

Open Twin XR has evaluated it as an importable source.

References:

- https://anatomytool.org/
- Open Twin XR resources: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/RESOURCES.md

Before incorporating any asset, its exact licence and the provenance of every sub-model must be verified.

---

# 6. Composition strategy

## 6.1 Do not build a "silent Frankenstein"

Wrong:

```text
female_hra.glb
+ male_biceps.obj
+ unrelated_ear.obj
+ generic_nerve.obj
---------------------
female_complete.glb
```

if everything is then presented as one coherent anatomical woman.

Right:

```text
Canonical female space
│
├── Primary donor geometry
│   ├── VHF imaging-derived geometry
│   ├── Denver VHF lower extremity
│   └── BMFToolkit / other VHF derivatives
│
├── Registered female donors
│   ├── TCIA female whole-body CT
│   ├── female CT/MRI datasets
│   └── female HRA reference structures
│
├── Specialist overlays
│   ├── OpenEar
│   ├── Human Organ Atlas
│   ├── Teeth3DS+
│   └── SPARC nerve scaffold
│
└── Template / inferred anatomy
    ├── Z-Anatomy
    ├── BodyParts3D
    └── other generic references
```

The UI must be able to show at any moment which category is being viewed.

---

# 7. Selection rule: "best source per structure"

Initial priority order:

1. **Same VHF donor + validated manual segmentation.**
2. Same VHF donor + reviewed automatic segmentation.
3. Another real woman, registered to the canonical space.
4. Female reference atlas.
5. Mixed dataset where the female specimen is identifiable.
6. Another human donor for structures with low sexual dimorphism.
7. Registered/deformed male model.
8. Illustrated/synthetic model.
9. Procedural geometry.

Examples:

```text
uterus
→ HRA Female / female donor data

left tibia
→ Denver Visible Human Female

intervertebral disc L4-L5
→ VHF segmentation or registered SPIDER geometry

cochlea
→ female CT segmentation if available
→ otherwise OpenEar specialist overlay

vagus nerve
→ SPARC scaffold + anatomical registration

missing small muscle
→ female segmentation
→ female donor dataset
→ only then registered Z-Anatomy/BodyParts3D
```

This priority must be **configurable per structure**.

---

# 8. Provenance per structure

Every anatomical object must carry a record such as:

```json
{
  "structure_id": "uberon:XXXXXXX",
  "name": "left biceps brachii",
  "fma": "FMA:XXXXX",
  "ta2": "XXXX",
  "source": "z-anatomy",
  "source_asset": "left_biceps_brachii",
  "source_sex": "male",
  "source_donor": "TARO",
  "canonical_space": "VHF",
  "geometry_type": "registered_template",
  "registration": {
    "type": "nonrigid",
    "transform_id": "..."
  },
  "confidence": 0.72,
  "license": "CC-BY-SA-4.0",
  "redistributable": true,
  "commercial_use": true,
  "notes": "Fallback: no validated female mesh currently available"
}
```

Possible values of `geometry_type`:

```text
measured
manual_segmentation
automatic_segmentation
registered_donor
registered_template
illustrated
procedural
specialist_overlay
```

---

# 9. Canonical ontology

Do not simply count "meshes".

A mesh does not necessarily equal an anatomical concept.

Build a canonical catalogue using mainly:

- UBERON;
- FMA;
- Terminologia Anatomica / TA2;
- HRA/CCF;
- SNOMED when useful for clinical crosswalk.

Sources:

- UBERON: https://uberon.github.io/
- FMA / BioPortal: https://bioportal.bioontology.org/ontologies/FMA
- HRA: https://humanatlas.io/
- HRA ontology: https://github.com/hubmapconsortium/hubmap-ontology
- HRA APIs: https://docs.hubmapconsortium.org/apis.html

---

# 10. Coverage Matrix

First piece of engineering to build.

Example:

| Structure | VHF | Denver | HRA ♀ | TCIA ♀ | CADS | SPIDER | OpenEar | SPARC | Z-Anatomy | BodyParts3D |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Biceps brachii | ? | ◐ | ? | ◐ | ✓ | — | — | ✓ | ✓ | ✓ |
| Tibia | ✓ | ✓ | ◐ | ✓ | ✓ | — | — | ✓ | ✓ | ✓ |
| Uterus | ✓/? | — | ✓ | ✓/? | ✓ | — | — | ✓ | — | — |
| Cochlea | ? | — | ◐ | ? | ✓ | — | ✓ | — | ✓ | ✓ |
| Disc L4-L5 | ? | — | ? | ? | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| Vagus nerve | ? | — | ? | ✗ | ? | — | — | ✓ | ✓ | ✓ |

Proposed legend:

```text
✓ geometry available
◐ partial coverage
~ possible derivation/segmentation
? pending verification
✗ not available
— out of the dataset's scope
```

The real matrix must be generated automatically from manifests and crosswalks.

---

# 11. Ingestion pipeline

```text
dataset
  ↓
licence audit
  ↓
source manifest
  ↓
ontology mapping
  ↓
coordinate normalization
  ↓
donor metadata
  ↓
mesh / labelmap import
  ↓
QA geometry
  ↓
registration
  ↓
anatomical QA
  ↓
LOD generation
  ↓
provenance metadata
  ↓
atlas registry
```

---

# 12. Spatial registration

Not all sources will share:

- scale;
- orientation;
- pose;
- proportions;
- topology;
- organ position.

So several levels are needed.

## 12.1 Rigid

For orientation and translation:

```text
rotation
translation
uniform scale
```

## 12.2 Affine

For small global differences:

```text
anisotropic scale
shear
```

## 12.3 Non-rigid

To register different donors:

- BCPD;
- thin-plate splines;
- diffeomorphic registration;
- landmark-driven warps;
- image registration where volumes exist.

HRA-AMAP is especially relevant:

https://github.com/cns-iu/hra-amap

---

# 13. New segmentations from images

This is a fundamental part of the project.

Where female imaging exists but no mesh:

```text
CT / MRI / cryosection
       ↓
segmentation model
       ↓
labelmap
       ↓
manual QA
       ↓
mesh extraction
       ↓
mesh QA
       ↓
ontology mapping
```

Candidate tools:

### MOOSE

- https://github.com/ENHANCE-PET/MOOSE

### TotalSegmentator

- https://github.com/wasserth/TotalSegmentator

### CADS

- https://github.com/murong-xu/CADS

### 3D Slicer

- https://www.slicer.org/

### VTK

- https://vtk.org/

---

# 14. Anatomical QA

Every incorporated geometry must pass at least:

## Geometry

- manifold where appropriate;
- normals;
- self-intersections;
- holes;
- degenerates;
- scale;
- orientation;
- reasonable volume.

## Anatomy

- laterality;
- connections;
- relative position;
- relations with bones;
- no impossible overlap;
- landmarks;
- vascular/nervous continuity.

## Registration

Store:

```text
source → canonical transform
landmarks used
RMS error
Hausdorff distance where applicable
volume distortion
surface distortion
review status
```

---

# 15. Multiresolution

Do not try to represent all anatomy in one GLB.

```text
LOD 0
whole body
        ↓
LOD 1
system / region
        ↓
LOD 2
organ / muscle / bone
        ↓
LOD 3
substructures
        ↓
LOD 4
microanatomy / specimen
```

Example:

```text
Female canonical body
    ↓
Temporal bone
    ↓
OpenEar specimen
    ↓
cochlea / ossicles / nerves
```

And:

```text
Female canonical body
    ↓
Kidney
    ↓
Human Organ Atlas kidney
    ↓
HiP-CT microvasculature
```

---

# 16. Licences: design the architecture around them

Do not mix all assets into one file without keeping each licence.

Proposal:

## Build 1 — `open-clean`

Only:

- public domain;
- CC0;
- CC BY;
- other compatible permissive licences.

Goal:

- redistribution;
- commercial use;
- maximum legal clarity.

## Build 2 — `open-sharealike`

Adds:

- CC BY-SA;
- ShareAlike-compatible components.

## Build 3 — `research-full`

May use datasets that are:

- CC BY-NC;
- CC BY-NC-SA;
- academic access;
- specific research licences.

Never redistribute assets whose licence does not allow it.

## Ambiguous assets

```text
unknown / no explicit licence
→ do not ship

ND
→ do not derive

NC
→ exclude from commercial build
```

---

# 17. Licence registry

Create a machine-readable `sources.json` or `licences.json`:

```json
{
  "openear": {
    "url": "https://zenodo.org/records/1473724",
    "license": "CC-BY-4.0",
    "redistributable": true,
    "commercial": true,
    "derivatives": true
  }
}
```

And every structure points to its source entry.

Before generating a release:

```bash
atlas check-licenses --target open-clean
atlas check-licenses --target open-sharealike
atlas check-licenses --target research-full
```

---

# 18. Proposed repository architecture

```text
female-open-human-atlas/
│
├── registry/
│   ├── sources.json
│   ├── licences.json
│   ├── donors.json
│   └── ontology-crosswalk.json
│
├── manifests/
│   ├── bodyparts3d.json
│   ├── hra-female.json
│   ├── visible-human-female.json
│   ├── denver-vhf.json
│   ├── tcia.json
│   ├── openear.json
│   └── ...
│
├── transforms/
│   └── source-to-vhf/
│
├── scripts/
│   ├── ingest/
│   ├── register/
│   ├── segment/
│   ├── mesh/
│   ├── qa/
│   └── build/
│
├── generated/
│   ├── coverage-matrix.json
│   ├── ontology-map.json
│   └── licence-report.md
│
├── public/
│   ├── atlases/
│   └── overlays/
│
└── docs/
    ├── ARCHITECTURE.md
    ├── DATASETS.md
    ├── ONTOLOGY.md
    ├── PROVENANCE.md
    ├── LICENSING.md
    └── COVERAGE.md
```

Large original data should stay out of Git and be downloaded by reproducible scripts.

---

# 19. UI

The viewer should allow switching between:

```text
Female canonical
Male canonical
Best available
Specific donor
Specific atlas
Compare
```

Per structure:

```text
Left tibia

Source:
Denver VHF

Donor:
Visible Human Female

Geometry:
manual segmentation → mesh

Canonical transform:
identity / VHF space

License:
...

Alternatives:
- TCIA Female 003
- BodyParts3D / TARO
- Z-Anatomy
```

---

# 20. Avoid two conceptual errors

## Error 1 — "female sex = swap the sexual organs"

No.

Differences can affect:

- pelvis;
- bone proportions;
- tissue distribution;
- thorax;
- musculature;
- skull;
- soft tissues;
- vascularisation;
- reproductive organs.

The goal must be **real female anatomy**, not a male atlas with a female reproductive system added.

## Error 2 — "complete model = one real person"

Also no.

A composite atlas can be more complete than any individual donor, but it must distinguish:

```text
measured donor anatomy
reference anatomy
registered donor anatomy
template-derived anatomy
```

---

# 21. Foreseeable gaps

Even combining the available datasets, these will probably remain hard:

- small peripheral nerves;
- complete plexuses;
- fine lymphatic network;
- fascia;
- tendon sheaths;
- retinacula;
- small structures of hands/feet;
- microvasculature;
- skin layers;
- certain connective tissues;
- small glands;
- structures that vary between individuals.

These gaps must appear explicitly in the Coverage Matrix.

---

# 22. Phases

## Phase 0 — Survey

Create an exhaustive inventory:

```text
dataset
URL
licence
modality
sex
donor
region
number of structures
ontology
format
resolution
redistribution
commercial OK
```

Result:

`DATASETS.md`

---

## Phase 1 — Ontology

Build the canonical universe:

```text
UBERON
+
FMA
+
TA2
+
HRA
```

Result:

```text
ontology-crosswalk.json
canonical-structures.json
```

---

## Phase 2 — Coverage Matrix

Cross all manifests.

Result:

```text
coverage-matrix.json
COVERAGE.md
```

Question it must answer:

> What is the best geometry available today for each anatomical structure?

---

## Phase 3 — VHF base

Ingest:

1. Visible Human Female.
2. Denver VHF.
3. BMFToolkit.
4. HRA Female.

Goal:

create the first **canonical female space**.

---

## Phase 4 — Full-body female scaffold

Add a complete female CT from:

Healthy-Total-Body-CTs.

Segment it with:

- published segmentations;
- MOOSE;
- TotalSegmentator;
- CADS where appropriate.

---

## Phase 5 — Specialised sources

Add:

- OpenEar;
- SPIDER;
- Teeth3DS+;
- SPARC;
- Human Organ Atlas;
- additional specialised datasets.

---

## Phase 6 — Fallback atlas

Only afterwards:

- Z-Anatomy;
- BodyParts3D;
- Open3Dmodel;
- other templates.

Every registered male structure must be clearly labelled.

---

## Phase 7 — QA

Automatic + anatomical review.

Output:

```text
qa-report.json
coverage-report.md
registration-report.md
licence-report.md
```

---

## Phase 8 — Web atlas

Reuse ideas from:

- human-atlas for UX;
- Open Twin XR for provenance/multi-atlas;
- Three.js / React for rendering.

---

# 23. Recommended MVP

Do not start by importing hundreds of gigabytes.

## MVP 1

Five sources:

1. HRA Female.
2. Denver VHF.
3. BMFToolkit.
4. TCIA female whole-body.
5. BodyParts3D only as reference/fallback.

Goal:

- reproducible pipeline;
- ontology mapping;
- provenance;
- registration;
- coverage matrix.

## MVP 2

Add:

- Z-Anatomy;
- SPARC;
- OpenEar;
- SPIDER;
- CADS.

## MVP 3

Multiresolution:

- Teeth3DS+;
- Human Organ Atlas / HiP-CT;
- additional specialised datasets.

---

# 24. What to measure

Do not use only:

```text
number_of_meshes
```

Measure:

```text
canonical concepts represented
anatomical systems covered
female-measured coverage
female-reference coverage
registered-female coverage
template-only coverage
structures without geometry
license-clean coverage
```

Example KPI:

```text
Total canonical structures:          5,200
Any geometry:                        4,850  93.3%
Female measured/segmented:           2,100  40.4%
Female reference/registered female:  3,650  70.2%
Male/generic template only:          1,200  23.1%
No geometry:                           350   6.7%
Commercial-clean build:              4,200  80.8%
```

---

# 25. Definition of success

The goal should not be:

> "to have a female model as complete as BodyParts3D".

It should be:

> **to create the most complete open female anatomical atlas that we can build from public and reproducible sources, knowing exactly where every structure comes from and without hiding where we had to resort to another donor, a male template or a reconstruction.**

And later:

```text
Female atlas
Male atlas
Generic atlas
Specific donors
Specialist specimens
```

all on the same ontology.

---

# 26. Main references

## Projects

- Human Atlas  
  https://github.com/ashemag/human-atlas

- Open Twin XR  
  https://github.com/Opening-Science/open-twin-xr

- Z-Anatomy  
  https://github.com/Z-Anatomy/Models-of-human-anatomy

---

## Base atlases and datasets

- BodyParts3D  
  https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html

- Human Reference Atlas  
  https://humanatlas.io

- HRA Female v1.5  
  https://lod.humanatlas.io/ref-organ/united-female/v1.5

- Visible Human Project  
  https://www.nlm.nih.gov/research/visible/visible_human.html

- Visible Human Female data  
  https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/index.html

- University of Denver Visible Human Female  
  https://digitalcommons.du.edu/visiblehuman/

- BMFToolkit  
  https://github.com/manishsreenivasa/BMFToolkit

- Healthy Total Body CTs  
  https://www.cancerimagingarchive.net/collection/healthy-total-body-cts/

---

## Specialised

- CADS  
  https://github.com/murong-xu/CADS

- SPIDER  
  https://github.com/cdoswald/SPIDER

- OpenEar  
  https://zenodo.org/records/1473724

- SPARC whole-body scaffold  
  https://discover.pennsieve.io/datasets/307

- Human Organ Atlas  
  https://human-organ-atlas.esrf.eu

- HiP-CT  
  https://mecheng.ucl.ac.uk/hip-ct/

- Teeth3DS+  
  https://crns-smartvision.github.io/teeth3ds/

---

## Segmentation / processing

- MOOSE  
  https://github.com/ENHANCE-PET/MOOSE

- TotalSegmentator  
  https://github.com/wasserth/TotalSegmentator

- 3D Slicer  
  https://www.slicer.org/

- VTK  
  https://vtk.org/

---

## Ontologies

- HRA  
  https://humanatlas.io

- HRA ontology  
  https://github.com/hubmapconsortium/hubmap-ontology

- UBERON  
  https://uberon.github.io/

- FMA / BioPortal  
  https://bioportal.bioontology.org/ontologies/FMA

---

# 27. Relevant papers / DOIs

- BodyParts3D  
  https://doi.org/10.1093/nar/gkn613

- Denver Visible Human lower extremities  
  https://doi.org/10.1038/s41597-022-01905-2

- Denver dataset  
  https://doi.org/10.56902/COB.vh.2022.0

- BMFToolkit / lower-body female meshes  
  https://arxiv.org/abs/1804.03655

- Healthy Total Body CTs  
  https://doi.org/10.7937/NC7Z-4F76

- SPIDER  
  https://doi.org/10.1038/s41597-024-03090-w

- SPARC whole-body model  
  https://doi.org/10.26275/BBVG-GJ86

- Teeth3DS+  
  https://arxiv.org/abs/2210.06094

- Human Organ Atlas  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC12978218/

---

# 28. First concrete task

Before downloading or modifying any mesh:

## Build `datasets.csv`

Columns:

```text
id
name
url
paper
license
license_url
redistributable
commercial_use
derivatives
modality
sex
donor_id
same_as_vhf
body_region
structures_count
ontology
format
resolution
download_size
access_restrictions
priority
notes
```

Then:

## Build `structures.csv`

```text
canonical_id
name
uberon
fma
ta2
system
laterality
```

And finally generate:

## `coverage.csv`

```text
canonical_structure
dataset
available
sex
donor
geometry_type
quality
license_class
priority
```

That will be the first artefact that tells us objectively **what we can build now, what we can derive and which anatomy still has no adequate open source**.

---

# 29. Execution status and next steps (5 September 2026, composition 0.4)

Local implementation: fork `human-atlas/`, branch `female-open-atlas`. Per-phase detail is in `docs/PROGRESS.md`; this section fixes the order of work.

## 29.1 Done

| Phase | Status | Evidence |
|---|---|---|
| 0 Survey | Almost complete | `datasets.csv` with 15 sources; licences verified with URL and date for 13 (NLM terms, SPIDER/OpenEar/HiP-CT CC BY 4.0, Teeth3DS CC BY-NC-ND, Z-Anatomy CC BY-SA, SPARC per dataset, BMFToolkit zlib with unconfirmed data scope). |
| 1 Ontology | Crosswalk with evidence | `registry/crosswalk-proposals.json` -> `scripts/build-crosswalk.py` (OLS) -> `registry/ontology-crosswalk-reviewed.json`: Denver 69/69, TCIA 35/36, NLM CT 114/117, HRA lateralized FMA 176/201, BodyParts3D 1,221/1,360; 168 unresolved. No anatomist review. |
| 2 Coverage | Automatic, merged | 4,263 entries; 248 with several sources; 22 merge Denver with HRA; individual / grouped / partial kinds; filters in the viewer. |
| 3 VHF base | Verified and extended | `VHF-image-2022` frame verified against the NLM CT headers (rigid same-donor pelvis registration: rotation 2.17°, free scale 1.0013, p95 4.72 mm). Trunk, upper limb and head of the VHF donor from the CT (114 TotalSegmentator labels, Apache-2.0). Denver at identity. |
| 4 CT scaffold | Two CTs | TCIA 003 (alternative source, not composed) and NLM VHF CT (composed). No mask review. |
| 5 Specialised | Licences verified | SPIDER, OpenEar, HiP-CT CC BY 4.0; Teeth3DS not distributable. Not imported. |
| 6 Fallback | Audited | BodyParts3D merged through the crosswalk as male reference; Z-Anatomy only fit for `open-sharealike`. |
| 7 QA | Extended automatic | Geometry, self-intersections, components, outliers (`Toes`), composite continuity, licences (3 targets, 4,415 references), review registries (`registry/review-status.json`, `registry/landmark-review.json`). No anatomical review. |
| 8 Web | Operational | Six sources, donor filter, registration review panel with 3D landmarks and exported decisions, side-by-side comparison, coverage with filters, ontology in provenance. |

Current KPIs (§24): 4,263 catalogued concepts; 128 female measured (Denver); 231 native in the canonical space (Denver + NLM CT); 114 female segmented from the same donor; 139 female segmented unreviewed; 717 female reference; 1,461 male template only; 1,880 without direct geometry; 1,712 meshes with an applied crosswalk; 4,415 clean mesh references for `open-clean`.

## 29.2 Immediate next step

**Done (2026-09-05): the VHF frame is verified and the trunk comes from the same donor.**

1. NLM VHF CT downloaded (1,734 slices, SHA-256), assembled into one RAS volume (two exams, junction shift 5.6 x 3.8 mm measured and recorded), segmented with TotalSegmentator `total` on CPU and rigidly registered to the Denver pelvis: `transforms/nlm-ct-to-vhf.json`, `generated/nlm-ct-registration.json`.
2. Composition 0.4: 1,015 meshes; Denver (128) + NLM CT (101; Denver replaces hip bones, sacrum, femora and gluteal/iliopsoas labels) + HRA (786; without skeleton or organs already covered by the CT). HRA fitted by six organ proxies onto the CT organs: RMS 7.42 mm (was 29.1 mm through TCIA). Head by the CT brain bounding box.
3. Acceptance: CT-Denver pelvis p95 < 5 mm **met** (4.72); scale 1 ± 1 % **met** (1.0013); rotation < 5° **met** (2.17); HRA proxy RMS < 30 mm **met** (7.42). TCIA lower-limb landmarks with one similarity **not met** (43.6 mm, pose), as before.

Pending in this phase: anatomical review of landmarks and labels, trunk posture between fresh CT and frozen block (unmeasured), appendicular bones and hands of the VHF donor (the TotalSegmentator `appendicular_bones` task needs a licence and is not used).

## 29.3 Next steps, in order

1. **Anatomical review**: landmarks (viewer export -> `registry/landmark-review.json`), CT label boundaries, HRA placement; refit only from confirmed landmarks.
2. **VHF cryosections with AI** (own project, `docs/plans/vhf-cryosection-segmentation-plan.md`): appendicular bones, hands, trunk and head of the same donor at 0.33 mm; measure the trunk posture between fresh CT and frozen block (vertebral landmarks).
3. **BMFToolkit**: send the request drafted in `docs/LICENSING.md`; import as a comparison source if the authors confirm.
4. **Specialised sources (MVP 2)**: select one female SPIDER study and one OpenEar specimen with documented sex; import as registered overlays in their own frames.
5. **Ontology**: review the 168 unresolved entries; import TA2.
6. **Dependencies**: assess the 11 upstream npm vulnerabilities.

## 29.4 Blockers and warnings

- Denver: download only through a real browser (`scripts/fetch-denver.py`, local Chrome); HTTP clients get 403 from Cloudflare.
- BMFToolkit: data licence scope unconfirmed; do not distribute.
- NLM VHF: terms verified; mandatory attribution "Courtesy of the U.S. National Library of Medicine"; derived data must state that they are not the current NLM data.
- TotalSegmentator: only the `total` task (Apache-2.0); licensed subtasks (appendicular_bones, tissue_types) are not used.
- The fits are automatic: the CT-Denver registration is rigid and tight at the pelvis, but the CT sacrum differs by 9.8 mm p95 and the femora rotated 1.6-3.0° at the hip between acquisitions; the trunk posture between fresh CT and cryosections is unmeasured.
- TCIA 003 has a different lower-limb pose (flexed knees) and is no longer part of the composite.
- `npm ci` reports 11 unassessed upstream vulnerabilities.
