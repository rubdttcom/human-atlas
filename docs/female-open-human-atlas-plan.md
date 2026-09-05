# Plan: atlas anatómico femenino abierto, compuesto y trazable

> **Objetivo:** construir un atlas anatómico femenino 3D abierto lo más completo posible combinando múltiples datasets, sin fingir que geometrías de distintos donantes constituyen una única persona real.  
> **Principio rector:** *best source per structure*, con procedencia, licencia, sexo/donante, método de registro y nivel de confianza almacenados por estructura.

**Estado del documento:** 5 de septiembre de 2026. Estado de ejecución y siguientes pasos en la sección 29 (al final).

---

## 1. Punto de partida

El proyecto [`ashemag/human-atlas`](https://github.com/ashemag/human-atlas) es un visor web 3D basado actualmente en **BodyParts3D 4.0**, con:

- 2.234 mallas OBJ seleccionables.
- 3.432 conceptos FMA en la jerarquía.
- anatomía de referencia masculina adulta;
- React + Three.js como capa de visualización;
- geometría simplificada y empaquetada para navegador.

El propio repositorio tuvo anteriormente una versión femenina basada en **Human Reference Atlas / HuBMAP Female v1.5**, con:

- 888 mallas;
- 1.073 nodos/conceptos;
- superficie corporal;
- órganos seleccionados;
- anatomía reproductiva femenina;
- cobertura parcial de músculo y esqueleto.

Referencia:

- Human Atlas: https://github.com/ashemag/human-atlas
- Attribution: https://github.com/ashemag/human-atlas/blob/main/public/ATTRIBUTION.md
- HRA Female v1.5: https://lod.humanatlas.io/ref-organ/united-female/v1.5
- HRA Female GLB: https://cdn.humanatlas.io/digital-objects/ref-organ/united-female/v1.5/assets/3d-vh-f-united.glb
- DOI HRA Female v1.5: https://doi.org/10.48539/HBM352.BTSQ.586

La limitación real no es que «no existan modelos femeninos abiertos», sino que **no existe un equivalente femenino único de BodyParts3D con la misma cobertura, granularidad y consistencia**.

---

## 2. Objetivo del nuevo proyecto

No buscar un único dataset ganador.

Construir un **atlas compuesto**:

```text
Female Open Human Atlas
│
├── espacio anatómico canónico femenino
│
├── geometría primaria del mismo donante cuando sea posible
│
├── geometrías de otros donantes registradas
│
├── overlays especializados de alta resolución
│
├── templates usados sólo como fallback
│
└── provenance + licencia + confianza por estructura
```

El atlas debe poder responder para cualquier estructura:

- ¿qué representa?
- ¿de qué dataset procede?
- ¿de qué donante procede?
- ¿sexo del donante?
- ¿es geometría medida, segmentada, registrada o inferida?
- ¿qué transformación se ha aplicado?
- ¿qué licencia tiene?
- ¿qué confianza tenemos en esa representación?
- ¿qué fuentes alternativas existen para esa misma estructura?

---

# 3. Precedente importante: Open Twin XR

[`Opening-Science/open-twin-xr`](https://github.com/Opening-Science/open-twin-xr) está desarrollando una estrategia muy parecida:

- varios atlas anatómicos registrados;
- varios donantes;
- composición «best per system»;
- provenance visible;
- separación entre atlas y overlays;
- ausencia representada como «no data» en lugar de inventar información;
- mapeo de estructuras a ontologías;
- auditoría de licencias;
- build publicable que puede excluir assets problemáticos;
- cuerpo femenino completo a partir de un CT de TCIA;
- BodyParts3D, Z-Anatomy, HRA, Visible Human, OpenEar y otras fuentes.

Referencias:

- Repo: https://github.com/Opening-Science/open-twin-xr
- Model pipeline: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/MODEL_PIPELINE.md
- Ontology map: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/ONTOLOGY_MAP.md
- Licence log: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/LICENCE_LOG.md
- Recursos: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/RESOURCES.md
- Registro de licencias: https://github.com/Opening-Science/open-twin-xr/blob/main/licences.json

**Recomendación:** no reinventar su trabajo de ingestión, registro, provenance y licencias. Usarlo como referencia arquitectónica e incluso evaluar reutilizar partes de su pipeline.

---

# 4. Espacio anatómico canónico

## 4.1 Propuesta

Usar **Visible Human Female (VHF)** como principal espacio de referencia femenino **donde sea posible**.

Razones:

- cuerpo femenino completo con cryosections;
- CT;
- MRI;
- resolución alta;
- existen datasets derivados independientes;
- permite crear nuevas segmentaciones cuando no exista una malla publicada.

NLM Visible Human Project:

- Página principal: https://www.nlm.nih.gov/research/visible/visible_human.html
- Acceso a datos: https://www.nlm.nih.gov/research/visible/getting_data.html
- Datos Female: https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/index.html

### Importante

No asumir que todos los modelos etiquetados como «HRA Female» son geometría segmentada directamente de una única mujer.

HRA es una **reference assembly** y el propio `human-atlas` advierte que su modelo femenino histórico:

> no es un escaneo completo de una única persona.

Por tanto:

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

# 5. Fuentes candidatas

## 5.1 BodyParts3D

### Aporta

- miles de estructuras anatómicas;
- fuerte cobertura general;
- identificadores FMA;
- excelente fuente para construir la ontología/manifest;
- útil como fallback geométrico.

### Limitación

- un único modelo masculino;
- no debe presentarse como anatomía femenina medida.

### Uso

- ontología y nomenclatura;
- referencia anatómica;
- último fallback geométrico;
- comparación male/female.

Referencias:

- Archivo oficial: https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html
- Licencia actual: https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html
- Paper: https://doi.org/10.1093/nar/gkn613
- Mirror/ tooling: https://github.com/Kevin-Mattheus-Moerman/BodyParts3D
- API / set moderno 4.x: https://github.com/olivercase/body_parts_3d_api

> Nota de licencia: copias históricas de BodyParts3D conservan texto CC BY-SA 2.1 Japan, mientras que el archivo oficial actual y `human-atlas` indican CC BY 4.0. La licencia debe verificarse contra la versión exacta de los assets usados.

---

## 5.2 Human Reference Atlas / HuBMAP

### Aporta

- modelos masculino y femenino;
- órganos de referencia;
- aparato reproductor femenino;
- terminología moderna;
- UBERON y conocimiento semántico;
- CCF/Common Coordinate Framework;
- APIs y knowledge graph.

### Uso

- órganos femeninos;
- ontología;
- sistema de coordenadas/registro;
- crosswalk semántico;
- referencia espacial.

Referencias:

- Portal HRA: https://humanatlas.io
- 3D Reference Library: https://humanatlas.io/3d-reference-library
- HRA UI: https://github.com/hubmapconsortium/hra-ui
- HRA registrations: https://github.com/hubmapconsortium/hra-registrations
- HRA API: https://apps.humanatlas.io/hra-api/
- APIs HuBMAP: https://docs.hubmapconsortium.org/apis.html
- HRA VCCF: https://github.com/hubmapconsortium/hra-vccf
- HRA-AMAP: https://github.com/cns-iu/hra-amap
- Female v1.5: https://lod.humanatlas.io/ref-organ/united-female/v1.5

---

## 5.3 Visible Human Female — NLM

### Aporta

- cryosections;
- CT;
- MRI;
- cuerpo completo;
- posibilidad de segmentar estructuras que ningún atlas haya publicado como malla.

### Uso

Debe ser el **ground truth volumétrico femenino principal** siempre que la licencia y la resolución de la estructura lo permitan.

Referencias:

- https://www.nlm.nih.gov/research/visible/visible_human.html
- https://www.nlm.nih.gov/research/visible/getting_data.html
- https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/index.html

---

## 5.4 University of Denver — Visible Human Female Lower Extremity

### Aporta

Geometrías musculoesqueléticas derivadas directamente del Visible Human Female:

- músculos;
- huesos;
- cartílago;
- ligamentos;
- grasa;
- pelvis → tobillo;
- STL originales;
- STL suavizados;
- modelos finales;
- máscaras de segmentación.

El conjunto masculino + femenino contiene 260 geometrías y, por sujeto:

- 76 músculos;
- 28 huesos;
- 16 cartílagos;
- 8 ligamentos;
- 2 geometrías de grasa.

### Uso

**Fuente primaria para tren inferior femenino**, con gran ventaja: deriva del mismo Visible Human Female que podemos usar como referencia volumétrica.

Referencias:

- Dataset: https://digitalcommons.du.edu/visiblehuman/
- Paper: https://doi.org/10.1038/s41597-022-01905-2
- DOI dataset: https://doi.org/10.56902/COB.vh.2022.0
- Herramientas FEMORS: https://github.com/thor-andreassen/femors

---

## 5.5 BMFToolkit

### Aporta

Mallas de alta resolución de huesos del tren inferior de una mujer adulta, derivadas de CT del Visible Human Dataset.

Incluye herramientas para:

- visualizar;
- remuestrear;
- modificar;
- escalar las mallas;
- landmarks;
- ejes articulares.

### Uso

Complemento/validación para:

- pelvis;
- pierna;
- pie;
- geometría ósea VHF.

Referencias:

- Repo: https://github.com/manishsreenivasa/BMFToolkit
- Paper: https://arxiv.org/abs/1804.03655

---

## 5.6 Healthy Total Body CTs — TCIA

### Aporta

30 adultos sanos con CT de cuerpo completo.

Incluye:

- sexo;
- altura;
- peso;
- BMI;
- CT;
- segmentaciones;
- 37 clases de tejidos;
- 13 órganos abdominales;
- 20 huesos;
- grasa subcutánea;
- grasa visceral;
- músculo esquelético;
- psoas.

Open Twin XR ya utiliza un **sujeto femenino** de este conjunto como cuerpo femenino completo.

### Uso

- scaffold femenino completo;
- completar regiones sin geometría VHF publicada;
- base para ejecutar segmentadores modernos;
- validación inter-donante.

Referencias:

- TCIA: https://www.cancerimagingarchive.net/collection/healthy-total-body-cts/
- DOI: https://doi.org/10.7937/NC7Z-4F76

### Licencia

- segmentaciones: CC BY 4.0;
- datos clínicos: CC BY 4.0;
- imágenes CT: sujetas a las condiciones de acceso de TCIA/NIH indicadas por la colección.

No asumir que todo el volumen puede redistribuirse junto con el atlas.

---

## 5.7 CADS

### Aporta

Modelo/dataset de segmentación CT con un espacio objetivo de aproximadamente **167 estructuras**.

Puede ayudar a generar:

- laringe;
- estructuras orbitarias;
- cóclea;
- columna;
- médula;
- costillas individualizadas;
- otras estructuras difíciles de obtener en atlas generales.

### Uso

No necesariamente como fuente de mallas.

Uso principal:

```text
CT femenino
    ↓
CADS
    ↓
labelmap
    ↓
mesh
    ↓
QA
```

Referencias:

- Repo/releases: https://github.com/murong-xu/CADS/releases

### Licencia

CADS publica distintas variantes de pesos bajo condiciones diferentes. El modelo de investigación se anuncia bajo CC BY-NC-SA 4.0; otros pesos añaden condiciones específicas procedentes de datasets de entrenamiento.

Debe auditarse **por release/modelo concreto**.

---

## 5.8 SPIDER

### Aporta

Dataset MRI lumbar:

- 447 series;
- 218 pacientes;
- vértebras;
- discos intervertebrales;
- canal espinal;
- segmentaciones manuales supervisadas.

### Uso

- columna lumbar;
- validación;
- geometrías de discos;
- canal espinal.

Referencias:

- Repo: https://github.com/cdoswald/SPIDER
- Paper: https://doi.org/10.1038/s41597-024-03090-w
- arXiv: https://arxiv.org/abs/2306.12217
- Challenge: https://spider.grand-challenge.org/

Licencia del dataset publicado: **CC BY 4.0**.

---

## 5.9 OpenEar

### Aporta

Ocho modelos 3D de hueso temporal humano basados en:

- CBCT;
- micro-slicing;
- datos de color;
- oído externo/medio/interno;
- cóclea;
- vestíbulo;
- osículos;
- tímpano;
- estructuras neurovasculares asociadas.

### Uso

**Overlay especializado**, no geometría base del cráneo femenino.

Debe conservar su tamaño/donante real y no deformarse silenciosamente para fingir que pertenece al donante canónico.

Referencias:

- Zenodo: https://zenodo.org/records/1473724
- Registro alternativo: https://zenodo.org/records/1342658

---

## 5.10 SPARC whole-body scaffold — Pennsieve Dataset 307

### Aporta

Modelo humano 3D integrado con:

- órganos;
- musculoesquelético;
- vasculatura;
- sistema nervioso;
- nerve centrelines.

### Uso

Muy interesante como **scaffold topológico para nervios y vasos**, incluso cuando la geometría visual final provenga de otras fuentes.

Referencias:

- Dataset: https://discover.pennsieve.io/datasets/307
- DOI: https://doi.org/10.26275/BBVG-GJ86

Licencia: **CC BY 4.0**.

---

## 5.11 Human Organ Atlas / HiP-CT

### Aporta

Imagen 3D multiescala de órganos humanos reales.

Resoluciones aproximadas:

- órgano completo: ~20 µm/voxel;
- regiones locales: hasta ~1 µm/voxel.

### Uso

No como cuerpo completo.

Sí como:

- overlay de alta resolución;
- detalle interno de órganos;
- nivel microscópico;
- fuente para segmentaciones especializadas.

Arquitectura:

```text
LOD 0  cuerpo
  ↓
LOD 1  órgano
  ↓
LOD 2  subestructura
  ↓
LOD 3  tejido / microanatomía
```

Referencias:

- Portal: https://human-organ-atlas.esrf.eu
- ESRF: https://www.esrf.fr/home/news/general/content-news/general/3d-atlas-of-human-organs-made-available-online.html
- UCL HiP-CT: https://mecheng.ucl.ac.uk/hip-ct/
- Bases de datos: https://mecheng.ucl.ac.uk/hip-ct/presentation/
- Paper: https://pmc.ncbi.nlm.nih.gov/articles/PMC12978218/

---

## 5.12 Teeth3DS+

### Aporta

Gran dataset de escaneos intraorales 3D:

- al menos 1.800 escaneos;
- 900 pacientes;
- maxilar y mandíbula;
- 23.999 dientes anotados;
- labels por vértice;
- identificación FDI.

### Uso

- dentición;
- atlas dental;
- diversidad morfológica;
- fuente para seleccionar/reconstruir dientes de referencia;
- validación de la anatomía dental.

No representa por sí mismo cráneo/maxilar completo.

Referencias:

- Web: https://crns-smartvision.github.io/teeth3ds/
- Dataset: https://osf.io/xctdy/
- Paper: https://arxiv.org/abs/2210.06094
- Challenge: https://github.com/abenhamadou/3dteethseg22_challenge

---

## 5.13 Z-Anatomy

### Aporta

Atlas anatómico de alta cobertura:

- musculoesquelético;
- sistema nervioso;
- cardiovascular;
- linfático;
- vísceras;
- regiones superficiales;
- múltiples estructuras que pueden faltar en datasets femeninos.

### Limitación fundamental

Su modelo humano principal es masculino y deriva parcialmente de BodyParts3D.

### Uso

**Template/fallback**, no fuente femenina primaria.

```text
estructura femenina disponible
    → usarla

no disponible
    → buscar otro dataset femenino

no disponible
    → template humano genérico

último fallback
    → Z-Anatomy / BodyParts3D registrado
```

Referencias:

- Organización: https://github.com/Z-Anatomy
- Modelos humanos: https://github.com/Z-Anatomy/Models-of-human-anatomy
- App histórica: https://github.com/LluisV/Z-Anatomy

### Licencias

Aunque el repositorio agregado declara CC BY-SA 4.0, contiene o referencia componentes de terceros con licencias diferentes, incluyendo algunos NC.

**Auditoría por estructura obligatoria.**

---

## 5.14 AnatomyTOOL / Open3Dmodel

### Aporta

Otra fuente de geometría anatómica reutilizable y potencialmente compatible como template.

Open Twin XR la ha evaluado como fuente importable.

Referencias:

- https://anatomytool.org/
- Open Twin XR resources: https://github.com/Opening-Science/open-twin-xr/blob/main/docs/RESOURCES.md

Antes de incorporar cualquier asset debe verificarse su licencia exacta y la procedencia de cada submodelo.

---

# 6. Estrategia de composición

## 6.1 No construir un “Frankenstein silencioso”

Incorrecto:

```text
female_hra.glb
+ male_biceps.obj
+ unrelated_ear.obj
+ generic_nerve.obj
---------------------
female_complete.glb
```

si después se presenta todo como una mujer anatómica coherente.

Correcto:

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

La UI debe poder indicar en cualquier momento qué categoría se está viendo.

---

# 7. Regla de selección: “best source per structure”

Orden de prioridad inicial:

1. **Mismo donante VHF + segmentación/manual validada.**
2. Mismo donante VHF + segmentación automática revisada.
3. Otra mujer real, registrada al espacio canónico.
4. Atlas femenino de referencia.
5. Dataset mixto donde el espécimen femenino sea identificable.
6. Otro donante humano para estructuras con bajo dimorfismo sexual.
7. Modelo masculino registrado/deformado.
8. Modelo ilustrado/sintético.
9. Geometría procedural.

Ejemplos:

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

Esta prioridad debe ser **configurable por estructura**.

---

# 8. Provenance por estructura

Cada objeto anatómico debe llevar un registro como:

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

Valores posibles de `geometry_type`:

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

# 9. Ontología canónica

No contar simplemente “mallas”.

Una malla no equivale necesariamente a un concepto anatómico.

Construir un catálogo canónico utilizando principalmente:

- UBERON;
- FMA;
- Terminologia Anatomica / TA2;
- HRA/CCF;
- SNOMED cuando sea útil para crosswalk clínico.

Fuentes:

- UBERON: https://uberon.github.io/
- FMA / BioPortal: https://bioportal.bioontology.org/ontologies/FMA
- HRA: https://humanatlas.io/
- HRA ontology: https://github.com/hubmapconsortium/hubmap-ontology
- HRA APIs: https://docs.hubmapconsortium.org/apis.html

---

# 10. Coverage Matrix

Primera pieza de ingeniería a construir.

Ejemplo:

| Estructura | VHF | Denver | HRA ♀ | TCIA ♀ | CADS | SPIDER | OpenEar | SPARC | Z-Anatomy | BodyParts3D |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Biceps brachii | ? | ◐ | ? | ◐ | ✓ | — | — | ✓ | ✓ | ✓ |
| Tibia | ✓ | ✓ | ◐ | ✓ | ✓ | — | — | ✓ | ✓ | ✓ |
| Útero | ✓/? | — | ✓ | ✓/? | ✓ | — | — | ✓ | — | — |
| Cóclea | ? | — | ◐ | ? | ✓ | — | ✓ | — | ✓ | ✓ |
| Disco L4-L5 | ? | — | ? | ? | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| Nervio vago | ? | — | ? | ✗ | ? | — | — | ✓ | ✓ | ✓ |

Leyenda propuesta:

```text
✓ geometría disponible
◐ cobertura parcial
~ posible derivación/segmentación
? pendiente de verificar
✗ no disponible
— fuera de alcance del dataset
```

La matriz real debe generarse automáticamente a partir de manifests y crosswalks.

---

# 11. Pipeline de ingestión

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

# 12. Registro espacial

No todas las fuentes compartirán:

- escala;
- orientación;
- postura;
- proporciones;
- topología;
- posición de órganos.

Por tanto necesitaremos varios niveles.

## 12.1 Rigid

Para orientación y traslación:

```text
rotation
translation
uniform scale
```

## 12.2 Affine

Para pequeñas diferencias globales:

```text
anisotropic scale
shear
```

## 12.3 Non-rigid

Para registrar donantes diferentes:

- BCPD;
- thin-plate splines;
- diffeomorphic registration;
- landmark-driven warps;
- image registration cuando existan volúmenes.

HRA-AMAP es especialmente relevante:

https://github.com/cns-iu/hra-amap

---

# 13. Nuevas segmentaciones a partir de imagen

Ésta es una parte fundamental del proyecto.

Cuando exista imagen femenina pero no malla:

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

Herramientas candidatas:

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

# 14. QA anatómico

Toda geometría incorporada debe superar al menos:

## Geometría

- manifold cuando sea apropiado;
- normales;
- self-intersections;
- holes;
- degenerates;
- escala;
- orientación;
- volumen razonable.

## Anatomía

- lateralidad;
- conexiones;
- posición relativa;
- relaciones con huesos;
- no solapamiento imposible;
- landmarks;
- continuidad vascular/nerviosa.

## Registro

Guardar:

```text
source → canonical transform
landmarks usados
error RMS
Hausdorff distance cuando aplique
volume distortion
surface distortion
review status
```

---

# 15. Multiresolución

No intentar representar toda la anatomía con un único GLB.

```text
LOD 0
cuerpo completo
        ↓
LOD 1
sistema / región
        ↓
LOD 2
órgano / músculo / hueso
        ↓
LOD 3
subestructuras
        ↓
LOD 4
microanatomía / espécimen
```

Ejemplo:

```text
Female canonical body
    ↓
Temporal bone
    ↓
OpenEar specimen
    ↓
cochlea / ossicles / nerves
```

Y:

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

# 16. Licencias: diseñar la arquitectura alrededor de ellas

No mezclar todos los assets en un único fichero sin conservar la licencia de cada uno.

Propuesta:

## Build 1 — `open-clean`

Sólo:

- public domain;
- CC0;
- CC BY;
- otras licencias permisivas compatibles.

Objetivo:

- redistribución;
- uso comercial;
- máxima claridad legal.

## Build 2 — `open-sharealike`

Añade:

- CC BY-SA;
- componentes compatibles con ShareAlike.

## Build 3 — `research-full`

Puede utilizar datasets:

- CC BY-NC;
- CC BY-NC-SA;
- acceso académico;
- licencias específicas de investigación.

Nunca redistribuir assets cuya licencia no lo permita.

## Assets ambiguos

```text
unknown / no explicit licence
→ do not ship

ND
→ do not derive

NC
→ exclude from commercial build
```

---

# 17. Registry de licencias

Crear un `sources.json` o `licences.json` machine-readable:

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

Y cada estructura apunta a su entrada de fuente.

Antes de generar release:

```bash
atlas check-licenses --target open-clean
atlas check-licenses --target open-sharealike
atlas check-licenses --target research-full
```

---

# 18. Arquitectura propuesta del repositorio

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

Los datos originales grandes deberían quedar fuera de Git y descargarse mediante scripts reproducibles.

---

# 19. UI

El visor debería permitir cambiar entre:

```text
Female canonical
Male canonical
Best available
Specific donor
Specific atlas
Compare
```

Por estructura:

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

# 20. Evitar dos errores conceptuales

## Error 1 — «sexo femenino = cambiar órganos sexuales»

No.

Las diferencias pueden afectar:

- pelvis;
- proporciones óseas;
- distribución de tejidos;
- tórax;
- musculatura;
- cráneo;
- tejidos blandos;
- vascularización;
- órganos reproductivos.

El objetivo debe ser una **anatomía femenina real**, no un atlas masculino con aparato reproductor femenino añadido.

## Error 2 — «modelo completo = una persona real»

Tampoco.

Un atlas compuesto puede ser más completo que cualquier donante individual, pero debe distinguir:

```text
measured donor anatomy
reference anatomy
registered donor anatomy
template-derived anatomy
```

---

# 21. Huecos previsibles

Incluso combinando los datasets disponibles, probablemente seguirán siendo difíciles:

- nervios periféricos pequeños;
- plexos completos;
- red linfática fina;
- fascia;
- vainas tendinosas;
- retináculos;
- estructuras pequeñas de manos/pies;
- microvasculatura;
- capas de piel;
- ciertos tejidos conectivos;
- glándulas pequeñas;
- estructuras variables entre individuos.

Estos huecos deben aparecer explícitamente en la Coverage Matrix.

---

# 22. Fases

## Fase 0 — Survey

Crear inventario exhaustivo:

```text
dataset
URL
licencia
modalidad
sexo
donante
región
nº estructuras
ontología
formato
resolución
redistribución
commercial OK
```

Resultado:

`DATASETS.md`

---

## Fase 1 — Ontología

Construir universo canónico:

```text
UBERON
+
FMA
+
TA2
+
HRA
```

Resultado:

```text
ontology-crosswalk.json
canonical-structures.json
```

---

## Fase 2 — Coverage Matrix

Cruzar todos los manifests.

Resultado:

```text
coverage-matrix.json
COVERAGE.md
```

Pregunta que debe responder:

> ¿Cuál es la mejor geometría disponible hoy para cada estructura anatómica?

---

## Fase 3 — VHF base

Ingestar:

1. Visible Human Female.
2. Denver VHF.
3. BMFToolkit.
4. HRA Female.

Objetivo:

crear el primer **canonical female space**.

---

## Fase 4 — Full-body female scaffold

Añadir un CT femenino completo de:

Healthy-Total-Body-CTs.

Segmentarlo con:

- segmentaciones publicadas;
- MOOSE;
- TotalSegmentator;
- CADS cuando corresponda.

---

## Fase 5 — Specialized sources

Añadir:

- OpenEar;
- SPIDER;
- Teeth3DS+;
- SPARC;
- Human Organ Atlas;
- datasets especializados adicionales.

---

## Fase 6 — Fallback atlas

Sólo después:

- Z-Anatomy;
- BodyParts3D;
- Open3Dmodel;
- otros templates.

Cada estructura masculina registrada debe quedar claramente etiquetada.

---

## Fase 7 — QA

Automática + revisión anatómica.

Salida:

```text
qa-report.json
coverage-report.md
registration-report.md
licence-report.md
```

---

## Fase 8 — Web atlas

Reutilizar ideas de:

- human-atlas para UX;
- Open Twin XR para provenance/multi-atlas;
- Three.js / React para rendering.

---

# 23. MVP recomendado

No empezar importando cientos de gigabytes.

## MVP 1

Cinco fuentes:

1. HRA Female.
2. Denver VHF.
3. BMFToolkit.
4. TCIA female whole-body.
5. BodyParts3D únicamente como referencia/fallback.

Objetivo:

- pipeline reproducible;
- ontology mapping;
- provenance;
- registration;
- coverage matrix.

## MVP 2

Añadir:

- Z-Anatomy;
- SPARC;
- OpenEar;
- SPIDER;
- CADS.

## MVP 3

Multiresolución:

- Teeth3DS+;
- Human Organ Atlas / HiP-CT;
- datasets especializados adicionales.

---

# 24. Qué medir

No usar sólo:

```text
number_of_meshes
```

Medir:

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

Ejemplo de KPI:

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

# 25. Definición de éxito

El objetivo no debería ser:

> «tener un modelo femenino tan completo como BodyParts3D».

Debería ser:

> **crear el atlas anatómico femenino abierto más completo que podamos construir con fuentes públicas y reproducibles, sabiendo exactamente de dónde procede cada estructura y sin ocultar dónde hemos tenido que recurrir a otro donante, a un template masculino o a una reconstrucción.**

Y, posteriormente:

```text
Female atlas
Male atlas
Generic atlas
Specific donors
Specialist specimens
```

todos sobre una misma ontología.

---

# 26. Referencias principales

## Proyectos

- Human Atlas  
  https://github.com/ashemag/human-atlas

- Open Twin XR  
  https://github.com/Opening-Science/open-twin-xr

- Z-Anatomy  
  https://github.com/Z-Anatomy/Models-of-human-anatomy

---

## Atlas y datasets base

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

## Especializados

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

## Segmentación / procesamiento

- MOOSE  
  https://github.com/ENHANCE-PET/MOOSE

- TotalSegmentator  
  https://github.com/wasserth/TotalSegmentator

- 3D Slicer  
  https://www.slicer.org/

- VTK  
  https://vtk.org/

---

## Ontologías

- HRA  
  https://humanatlas.io

- HRA ontology  
  https://github.com/hubmapconsortium/hubmap-ontology

- UBERON  
  https://uberon.github.io/

- FMA / BioPortal  
  https://bioportal.bioontology.org/ontologies/FMA

---

# 27. Papers / DOI relevantes

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

# 28. Primera tarea concreta

Antes de descargar o modificar ninguna malla:

## Construir `datasets.csv`

Columnas:

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

Después:

## Construir `structures.csv`

```text
canonical_id
name
uberon
fma
ta2
system
laterality
```

Y finalmente generar:

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

Ése será el primer artefacto que nos dirá objetivamente **qué podemos construir ya, qué podemos derivar y qué anatomía sigue sin una fuente abierta adecuada**.

---

# 29. Estado de ejecución y siguientes pasos (5 de septiembre de 2026)

Implementación local: fork `human-atlas/`, rama `female-open-atlas`. El detalle por fase está en `docs/PROGRESS.md`; este apartado fija el orden de trabajo.

## 29.1 Hecho

| Fase | Estado | Evidencia |
|---|---|---|
| 0 Survey | Parcial | `datasets.csv` con 14 fuentes; licencias verificadas sólo para HRA, BodyParts3D, TCIA y Denver. |
| 1 Ontología | Mínima | `structures.csv` = unión de IDs importados (FMA/UBERON heredados, etiquetas locales TCIA y Denver). Sin crosswalk revisado. |
| 2 Coverage | Automática | `generated/coverage-matrix.json`, 4.316 entradas; filtro "female measured" en el visor. |
| 3 VHF base | Parcial | Denver VHF importado (128 mallas, miembro inferior, marco de imagen VHF). HRA importado. BMFToolkit inventariado, no distribuido. NLM VHF no descargado. |
| 4 CT scaffold | Parcial | TCIA 003 (36 etiquetas publicadas). Sin segmentación nueva. |
| 5 Especializadas | No iniciada | — |
| 6 Fallback | Parcial | BodyParts3D como referencia masculina separada. |
| 7 QA | Automática | Geometría, procedencia, licencias (3 targets), composición, navegador. Sin revisión anatómica. |
| 8 Web | Operativa | Cinco fuentes, composición experimental 0.2 (938 mallas), procedencia por malla, cobertura. |

KPIs actuales (§24): 4.316 conceptos catalogados; 128 medidos femeninos; 36 segmentados femeninos sin revisar; 717 referencia femenina; 1.589 sólo template masculino; 1.846 sin geometría directa; 4.224 referencias de malla limpias para `open-clean`.

## 29.2 Siguiente paso inmediato

**Convertir el marco de imagen VHF en el espacio canónico femenino.**

1. Declarar `canonical_space = "VHF-image-2022"` (marco alineado de Denver, mm → m, ejes ya verificados).
2. Invertir la composición: registrar TCIA 003 → VHF y HRA → VHF, en vez de Denver → TCIA. Denver queda con transformación identidad y `canonical_registration: true`.
3. Sustituir los centros de cajas por landmarks óseos marcados a mano en Denver y TCIA: espinas ilíacas anterosuperiores, cabezas femorales, epicóndilos, maléolos, tuberosidades isquiáticas. Guardarlos en `transforms/landmarks/*.json` con quién los marcó y en qué vista.
4. Recalcular residuos, añadir distancia de superficie (Hausdorff) hueso a hueso donde TCIA y Denver comparten estructura (fémur, tibia, peroné, pelvis).
5. Criterio de cierre: residuo RMS < 15 mm en miembro inferior y ningún hueso Denver fuera de la envolvente ósea TCIA correspondiente.

Motivo: el plan (§4) define VHF como espacio canónico; hoy el compuesto usa TCIA 003 como marco provisional y ninguna fuente está registrada a VHF.

## 29.3 Siguientes pasos, en orden

1. **Espacio canónico VHF** (29.2).
2. **Crosswalk ontológico revisado** para las 128 etiquetas Denver y las 36 TCIA hacia UBERON/FMA (sin adivinar IDs; anotar evidencia por término). Con ello, fusionar en la matriz de cobertura los huesos Denver con los de HRA/TCIA y recalcular los KPIs de §24.
3. **NLM Visible Human Female**: verificar términos exactos, descargar CT (y criosecciones si procede), y ejecutar TotalSegmentator/MOOSE para obtener tronco, miembro superior y cabeza en el mismo donante y marco que Denver. Esto reduce la mezcla de donantes en el compuesto.
4. **BMFToolkit**: resolver el alcance de licencia de los datos (contacto autores / registro Zenodo); si es CC, importar y comparar hueso a hueso con Denver en el marco VHF, marcando explícitamente las mallas reflejadas.
5. **Revisión anatómica y QA**: autointersecciones, continuidad cervical del ajuste craneal, lista de outliers (p. ej. `Toes` de TCIA), y estado `reviewed` por estructura.
6. **Fuentes especializadas (MVP 2)**: OpenEar, SPIDER, Teeth3DS+, SPARC, HiP-CT. Primero licencia y metadatos de donante; después importación como overlays multiresolución.
7. **UI**: modo "best available" por estructura, filtro por donante, comparación lado a lado de fuentes alternativas, controles de revisión de registro.
8. **Fallbacks (Fase 6)**: auditar Z-Anatomy/Open3Dmodel componente a componente antes de incluir nada.

## 29.4 Bloqueos y avisos

- Denver: descarga sólo mediante navegador real (`scripts/fetch-denver.py`, Chrome local); los clientes HTTP reciben 403 de Cloudflare.
- BMFToolkit: licencia de datos no acreditada; no distribuir.
- NLM VHF: términos exactos sin verificar; no descargar hasta hacerlo.
- Los ajustes actuales (RMS 27–28 mm) son experimentales y no acreditan registro anatómico.
- `npm ci` reporta 11 vulnerabilidades upstream sin evaluar.

