# Dataset inventory

Candidate status is not proof of import. Detailed metadata and open questions are in `datasets.csv`.

| Source | Sex | Donor | Licence position | Priority |
| --- | --- | --- | --- | --- |
| [HRA United Female v1.5](https://lod.humanatlas.io/ref-organ/united-female/v1.5) | female | multiple-or-unknown | CC-BY-4.0 | 4 |
| [Denver Visible Human Female 2022](https://digitalcommons.du.edu/visiblehuman/1/) | female | VHF | CC-BY-4.0 | 1 |
| [Bone Mesh Female Toolkit v1.0](https://github.com/manishsreenivasa/BMFToolkit) | female | VHF | UNVERIFIED-ASSET | 1 |
| [NLM Visible Human Female](https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/index.html) | female | VHF | UNVERIFIED | 1 |
| [Healthy Total Body CTs segmentations January 2023](https://www.cancerimagingarchive.net/collection/healthy-total-body-cts/) | female | Healthy-Total-Body-CTs-003 | CC-BY-4.0 | 3 |
| [BodyParts3D 4.0 via human-atlas](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html) | male | TARO | CC-BY-4.0 | 7 |
| [SPIDER lumbar MRI](https://github.com/cdoswald/SPIDER) | mixed | unselected | UNVERIFIED | 5 |
| [OpenEar v2](https://zenodo.org/records/1473724) | unknown | eight specimens | UNVERIFIED | 6 |
| [SPARC whole-body scaffold 307](https://discover.pennsieve.io/datasets/307) | reference | reference | UNVERIFIED | 6 |
| [Human Organ Atlas HiP-CT](https://human-organ-atlas.esrf.eu) | mixed | unselected | PER-ASSET | 6 |
| [Teeth3DS+](https://crns-smartvision.github.io/teeth3ds/) | unknown | unselected | UNVERIFIED | 6 |
| [Z-Anatomy](https://github.com/Z-Anatomy/Models-of-human-anatomy) | male | multiple-or-unknown | PER-ASSET | 7 |
| [AnatomyTOOL Open3Dmodel](https://anatomytool.org/) | unknown | unknown | PER-ASSET | 8 |
| [CADS](https://github.com/murong-xu/CADS/releases) | not-applicable | not-applicable | PER-MODEL | 3 |

Imported: HRA female, BodyParts3D male, TCIA 003 published segmentations and the Denver VHF final STL models (128 lower-limb meshes).
BMFToolkit is inventoried but not shipped. Denver assets sit behind a Cloudflare challenge: plain HTTP clients get HTTP 403, so `scripts/fetch-denver.py` uses a local Chrome session. All other candidate imports remain pending.
