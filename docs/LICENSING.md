# Licensing

Original application code remains MIT. Included HRA, BodyParts3D, TCIA
segmentation and Denver VHF geometry retain CC BY 4.0 attribution and documented adaptations in
`public/ATTRIBUTION.md`. Inputs are recorded separately from derived geometry.

The TCIA public segmentation and clinical table are distinct from the CT images;
the latter were not downloaded. BMFToolkit software is zlib and its Zenodo record
says `other-open`; asset-specific scope remains unresolved. No BMFToolkit geometry
is in the public build. Other candidate terms remain per-asset audit items.

`./atlas check-licenses --target open-clean`, `open-sharealike` and `research-full`
inspect every mesh referenced by the shipped atlases. Unknown or incompatible
terms fail the selected target. These checks do not approve candidate sources or
certify legal or anatomical conclusions beyond the recorded evidence.
