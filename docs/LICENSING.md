# Licensing

Original application code remains MIT. Included HRA, BodyParts3D, TCIA segmentation and
Denver VHF geometry retain CC BY 4.0 attribution and documented adaptations in
`public/ATTRIBUTION.md`. Inputs are recorded separately from derived geometry.

## NLM Visible Human Female CT and its derived labels

The NLM image data are U.S. Government works released under the NLM Terms and Conditions
(https://www.nlm.nih.gov/databases/download/terms_and_conditions.html, verified 2026-09-05
and stored in `data/raw/nlm-vhf/terms_and_conditions.html`). No licence or registration has
been required since July 2019. Users must acknowledge NLM ("Courtesy of the U.S. National
Library of Medicine"), must not imply NLM endorsement, and redistributed derived data must
state that they do not reflect the current NLM data. The label maps are TotalSegmentator
output from the `total` task, which the project README declares "openly available for any
usage (Apache-2.0 license)"; licensed subtasks (appendicular bones, tissue types, heart
chambers) were not used. The licence checker accepts `NLM-Terms-and-Conditions` in every
target on this basis. Derived labels are automatic and unreviewed; that is stated in every
record and in the viewer.

## BMFToolkit

The repository LICENSE is the zlib licence text ("this software"), with no separate data
terms; the Zenodo record 889060 says `other-open`; GitHub reports `NOASSERTION`. Whether the
authors intend the zlib terms to cover the mesh data in `data/` is not stated, so no
BMFToolkit geometry is in the public build. The bone-by-bone comparison with Denver
(`generated/bmftoolkit-comparison.json`) redistributes only measurements.

Prepared request to the authors (not sent; sending is the maintainer's decision):

> Subject: Licence scope of the BMFToolkit bone meshes
>
> Dear Dr Sreenivasa and Dr Gonzalez-Alvarado,
>
> We are assembling an open female anatomical atlas from published open datasets, with a
> provenance record for every mesh (https://github.com/ashemag/human-atlas fork, branch
> female-open-atlas). BMFToolkit's lower-body bone meshes of the Visible Human Female are a
> valuable comparison to the University of Denver cryosection segmentation of the same donor.
> Your repository LICENSE carries the zlib licence, whose text refers to "this software".
> Could you confirm whether the mesh data in `data/model_Original.mat` may be redistributed
> under the same zlib terms (or under a Creative Commons licence of your choice), with
> attribution to your publication? We will record your answer verbatim in the atlas licence
> evidence and not redistribute the meshes until then.
>
> Thank you for making the toolkit available.

## Other candidates

Teeth3DS is CC BY-NC-ND 4.0: simplified or re-exported meshes are derivatives, so it cannot
be shipped in any target. SPIDER (Zenodo 10159290), OpenEar (Zenodo 1473724) and HiP-CT
(ESRF DataCite records) are CC BY 4.0; specimen sex and frames must be read from the
publications before import. Z-Anatomy is CC BY-SA 4.0 and derived from the male
BodyParts3D; it could only enter the `open-sharealike` target. SPARC datasets are licensed
individually (Creative Commons Attribution for the human scaffolds checked). Verification
dates and evidence URLs are in `datasets.csv`.

`./atlas check-licenses --target open-clean`, `open-sharealike` and `research-full`
inspect every mesh referenced by the shipped atlases. Unknown or incompatible terms fail
the selected target. These checks do not approve candidate sources or certify legal or
anatomical conclusions beyond the recorded evidence.
