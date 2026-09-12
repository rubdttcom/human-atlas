# Reproduce the local atlas

Use Node 22.13+ and two Python environments: `.venv` with the pinned pipeline packages in
`requirements-pipeline.txt`, and `.venv-seg` with TotalSegmentator (CPU build of torch;
the exact versions used are recorded in `generated/nlm-ct-registration.json` and in the
source records: TotalSegmentator 2.18.0, torch 2.14.0+cpu, torchvision 0.29.0+cpu).
The fork retains original source manifests and binary geometry alongside derived atlas
manifests. HRA binaries come from the pinned historical upstream revision.

```bash
npm ci
python3 -m venv .venv
.venv/bin/pip install -r requirements-pipeline.txt
python3 -m venv .venv-seg
.venv-seg/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv-seg/bin/pip install totalsegmentator==2.18.0

# TCIA 003 (published segmentation) and Denver VHF (final STL models)
.venv/bin/python scripts/fetch-tcia.py
.venv/bin/python scripts/ingest-tcia.py
node scripts/optimize-anatomy.mjs atlas-tcia-female.json tcia-003-lod
node scripts/compress-models.mjs atlas-tcia-female.json
.venv/bin/python scripts/fetch-denver.py
.venv/bin/python scripts/ingest-denver.py
node scripts/optimize-anatomy.mjs atlas-denver-female.json denver-vhf-lod
node scripts/compress-models.mjs atlas-denver-female.json
python3 scripts/build-registry.py

# NLM Visible Human Female fresh CT: download, assemble, segment, register to Denver, ingest
.venv/bin/python scripts/fetch-nlm-vhf.py
.venv/bin/python scripts/build-nlm-vhf-volume.py
.venv-seg/bin/python -c "import json; from totalsegmentator.map_to_binary import class_map; json.dump({'total': class_map['total']}, open('data/derived/nlm-vhf/totalseg-classmap.json', 'w'), indent=1)"
OMP_NUM_THREADS=20 .venv-seg/bin/TotalSegmentator -i data/derived/nlm-vhf/vhf-fresh-ct.nii.gz -o data/derived/nlm-vhf/totalseg --ml -d cpu
.venv/bin/python scripts/register-nlm-ct.py data/derived/nlm-vhf/totalseg.nii
.venv/bin/python scripts/ingest-nlm-vhf.py data/derived/nlm-vhf/totalseg.nii
node scripts/optimize-anatomy.mjs atlas-nlm-vhf-ct.json nlm-vhf-ct-lod
node scripts/compress-models.mjs atlas-nlm-vhf-ct.json

# CT consensus source (vertebrae, sacrum, ribs voted per geometric instance; needs the MOOSE and Skellytour copies described below)
.venv-seg/bin/python scripts/ct-vertebra-instances.py nlm vertebrae --selftest
.venv-seg/bin/python scripts/ct-vertebra-instances.py nlm ribs_left --selftest
.venv-seg/bin/python scripts/ct-vertebra-instances.py nlm ribs_right --selftest
.venv/bin/python scripts/ingest-ct-consensus.py
node scripts/optimize-anatomy.mjs atlas-ct-consensus.json ct-consensus-lod
node scripts/compress-models.mjs atlas-ct-consensus.json

# Ontology crosswalk (OLS evidence), registry, landmarks, composition, QA, reports
.venv/bin/python scripts/build-crosswalk.py          # add --offline to reuse generated/ols-cache.json
python3 scripts/build-registry.py
.venv/bin/python scripts/extract-landmarks.py
.venv/bin/python scripts/compose-female.py
.venv/bin/python scripts/qa-geometry.py
.venv/bin/python scripts/qa-anatomy.py               # about 45 min on 20 cores from scratch; reuses measurements of byte-identical meshes (geometry_sha256), so a rebuild that changes one source takes minutes
.venv/bin/python scripts/compare-bmftoolkit.py       # needs sources/BMFToolkit checked out; nothing is shipped
python3 scripts/build-registry.py                   # also refreshes QA metadata in composed.json
.venv/bin/python scripts/test-qa-carryover.py
.venv/bin/python scripts/summarize-reports.py
```

## Shortcut: download the prepared data from the GitHub release

The release `data-2026-09-05` (https://github.com/rubdttcom/human-atlas/releases/tag/data-2026-09-05)
holds the source archives and the intermediate NLM CT volume and TotalSegmentator label maps
(412 MB in total, with `SHA256SUMS`). With them you can skip the downloads from the original
servers and the 35 minute segmentation:

```bash
gh release download data-2026-09-05 --repo rubdttcom/human-atlas --dir /tmp/atlas-data
(cd /tmp/atlas-data && sha256sum -c SHA256SUMS)
mkdir -p data/derived/nlm-vhf data/raw/nlm-vhf data/raw/denver data/raw/tcia
cp /tmp/atlas-data/vhf-fresh-ct.nii.gz /tmp/atlas-data/vhf-fresh-ct-metadata.json /tmp/atlas-data/totalseg-classmap.json data/derived/nlm-vhf/
gunzip -c /tmp/atlas-data/totalseg.nii.gz > data/derived/nlm-vhf/totalseg.nii
cp /tmp/atlas-data/nlm-download-manifest.json data/raw/nlm-vhf/download-manifest.json
cp /tmp/atlas-data/denver-final-stl-models.zip data/raw/denver/final-stl-models.zip
cp /tmp/atlas-data/denver-metadata.zip data/raw/denver/metadata.zip
cp /tmp/atlas-data/denver-download-manifest.json data/raw/denver/download-manifest.json
cp /tmp/atlas-data/Healthy-Total-Body-CTs-003.nii.gz data/raw/tcia/
cp /tmp/atlas-data/tcia-demographics.xlsx data/raw/tcia/demographics.xlsx
cp "/tmp/atlas-data/tcia-segmentation_organ_values.xlsx" "data/raw/tcia/segmentation_organ_values (1).xlsx"
cp /tmp/atlas-data/tcia-download-manifest.json data/raw/tcia/download-manifest.json
```

Then run the pipeline from `scripts/ingest-tcia.py` and `scripts/ingest-denver.py`, skip
`fetch-nlm-vhf.py`, `build-nlm-vhf-volume.py` and TotalSegmentator, and continue at
`scripts/register-nlm-ct.py`. The NLM slices themselves (478 MB) are not in the release;
`scripts/fetch-nlm-vhf.py` re-downloads them and checks them against the manifest.

## What each new step does

`fetch-nlm-vhf.py` downloads the NLM Terms and Conditions page, the Female-Images README
and INDEX, and the 1,734 fresh-CT slices with their GE header dumps (`data/raw/nlm-vhf/`,
SHA-256 per file in `download-manifest.json`). No licence or registration is needed
since July 2019; the terms require the attribution "Courtesy of the U.S. National Library
of Medicine" and a statement that derived data are not the current NLM data.

`build-nlm-vhf-volume.py` parses every header (pixel size, plane centre, table position),
finds the two exams (370: vertex to thigh, 371: thigh to feet; the table was re-zeroed
between them), resamples every slice onto one 480 mm field of view and stacks them at
1 mm in file order into `data/derived/nlm-vhf/vhf-fresh-ct.nii.gz` (RAS millimetres).
It measures the in-plane shift across the exam junction by phase correlation (recorded,
not corrected) and converts stored values to Hounsfield units by the air offset.

TotalSegmentator's `total` task (117 classes, Apache-2.0) is run on the CPU; the licensed
subtasks (appendicular bones, tissue types) are not used. The multi-label output is
`data/derived/nlm-vhf/totalseg.nii`. `--fast` (3 mm) reproduces the pipeline in a few
minutes for testing; the shipped geometry uses the full 1.5 mm model.

`register-nlm-ct.py` extracts the CT hip bones, sacrum and femora, registers the pelvis
rigidly (no scale) onto the Denver hip bones and sacrum of the same donor in the VHF
image frame, repeats the fit with a free scale as a unit check, and fits each femur on its
own to measure the hip pose change between acquisitions. It writes
`transforms/nlm-ct-to-vhf.json` and `generated/nlm-ct-registration.json`; the report's
`canonical_space_verification` block is the evidence that `VHF-image-2022` agrees with
the NLM image headers in axes and units.

`ingest-nlm-vhf.py` converts every present label to viewer geometry already expressed in
the canonical stage (voxel -> CT RAS -> `nlm-ct-to-vhf` -> `denver-image-to-stage`), with
the label value, model, registration and hashes in every source record.

`build-crosswalk.py` verifies `registry/crosswalk-proposals.json` against the EBI Ontology
Lookup Service and writes `registry/ontology-crosswalk-reviewed.json` with the OLS record
per term; `build-registry.py` uses only entries marked `applied`. Lateralized FMA terms of
HRA and BodyParts3D are resolved to their generic FMA parent and to UBERON when the UBERON
term cross-references that FMA identifier.

`extract-landmarks.py` computes pelvic, knee and ankle bone landmarks on the Denver,
TCIA 003 and HRA meshes by explicit geometric rules and writes them to
`transforms/landmarks/*.json` with `manual_review: pending`. `compose-female.py` builds
composition 0.4: Denver at identity, the same-donor CT labels at identity (Denver bones and
gluteal/iliopsoas muscles replace their CT labels), HRA detail fitted on organ proxies onto
the CT organs, head fitted into the CT brain envelope; TCIA 003 is registered but not
composed. It writes `transforms/*-stage-to-vhf.json`, `public/atlases/composed.json` and
`generated/registration-report.json`.

`qa-anatomy.py` counts self-intersecting triangle pairs per mesh, flags connected
components far from the main component and measures bounding-box continuity of the
composite. Run it after every `qa-geometry.py`: the geometry pass only carries measured
self-intersection and component counts over for meshes whose geometry is byte-identical to
the previous report and marks everything else `not-assessed`, so a rebuild that skips the
anatomy pass ships `not-assessed` into the manifests. Identity is the SHA-256 of the shipped
bytes (`geometry_sha256`, `scripts/qa_identity.py`); aggregate statistics never count, and a
row without a digest is never carried over. A report that predates the field is migrated
with `scripts/qa-hash-revision.py REV REPORT OUT`, which digests the buffers of the git
revision that produced it (the 4,415 rows measured at f830ea5 were checked this way: all
carried rows are byte-identical to that revision). `scripts/test-qa-carryover.py` is the
regression test (two boxes with equal statistics and different geometry). The anatomy pass
reuses previous measurements of identical meshes and recomputes the rest; the spine selector
accepts `role: vertebra` (ct-consensus instances `V01..V25`) as well as `vertebrae_*` labels
and stops if CT parts exist but no vertebra matches. `build-registry.py`, run after both
passes, refreshes `public/atlases/composed.json`: every composed part carries `geometry_qa`
(the source mesh) and `composed_geometry_qa` (the transformed copy) from the current report,
and `validate-composition.py` checks both digests against the shipped buffers. `compare-bmftoolkit.py` aligns every BMFToolkit bone to its Denver counterpart
by rigid ICP and records the residuals; BMFToolkit geometry is never written to `public/`.

## Verification

```bash
node scripts/validate-atlas.mjs
node scripts/validate-atlas.mjs atlas-female.json
node scripts/validate-atlas.mjs atlas-tcia-female.json
node scripts/validate-atlas.mjs atlas-denver-female.json
node scripts/validate-atlas.mjs atlas-nlm-vhf-ct.json
node --experimental-strip-types scripts/validate-interactions.mjs
python3 scripts/validate-provenance.py
.venv/bin/python scripts/validate-composition.py
.venv/bin/python scripts/validate-reviews.py
./atlas check-licenses --target open-clean
./atlas check-licenses --target open-sharealike
./atlas check-licenses --target research-full
npx tsc --noEmit
npm run build
npx vite --port 3017
```

The dev server or a static server of `dist/` (`npm run build && (cd dist && python3 -m http.server 3017 --bind 127.0.0.1)`) must listen on port 3017. In another terminal, run `.venv/bin/python scripts/browser-check.py`. The script uses
`/usr/bin/google-chrome` and writes screenshots and canvas-pixel evidence to
`artifacts/browser/`; it now also exercises the donor filter, the registration review
panel with the landmark overlay and the coverage filters on the composite.

To change individual composition choices, set source record IDs to boolean values in
`registry/composition-overrides.json`, then rerun composition and its verifier. Reviewer
decisions go to `registry/review-status.json` and `registry/landmark-review.json` (the
viewer's Registration review panel exports the latter); `validate-reviews.py` checks them.
Overrides select geometry; they do not validate its registration.

Keep `data/derived/` and `.venv-seg/` ignored by Git (they are in `.gitignore`): Tailwind's source scanner reads every non-ignored file, and the 800 MB NIfTI volumes stall `vite build` and the dev server for tens of minutes.

Neither counts nor licence eligibility imply anatomical correctness.

## GPU runs on the CT priors (plan B, stage 1)

The three CT bone models run on a separate machine with an RTX 3080 (10 GB) and 31 GB RAM; the
scripts in `scripts/gpu/` are copied there and run under `/media/rub/Backups/VHF/` (variable `BASE`).
All pin the GPU by UUID through `CUDA_VISIBLE_DEVICES`.

| Script | Model | Input | Output on the GPU box | Copy in the repo |
| --- | --- | --- | --- | --- |
| `run-moose.sh` | MOOSE 3.2.2, four bone models | `nlm-vhf/derived/vhf-fresh-ct.nii.gz` | `moose/input/vhf/moosez-*/segmentations/` | `data/derived/nlm-vhf/moose/` |
| `run-denver-ct-priors.sh` | MOOSE bones, then TotalSegmentator `total` | Denver aligned CT (HU + 1000 -> HU) | `denver/priors/{moose,totalseg}/` | `data/derived/denver/priors/` (TotalSegmentator was rerun locally on CPU after the GPU run was killed by RAM) |
| `run-skellytour-chunked.sh nlm denver` | Skellytour `high` | both CTs | `skellytour/{nlm,denver}/skellytour_high.nii.gz` | `data/derived/nlm-vhf/skellytour/`, `data/derived/denver/priors/skellytour/` |
| `merge-skellytour.py` | the only stitching of Skellytour chunks (called by the shell script): postprocessed output preferred, **stops** on a missing or ambiguous chunk (`--allow-missing` only lists them and marks the manifest incomplete, never zero-fills silently), writes per-chunk file, SHA-256 and labels, the crop box (unprocessed region) and the label agreement across every seam | chunk outputs | `skellytour_high.{nii.gz,json}` | same |

Skellytour `high` needs about 38 GB RAM per 109 L of CT (its own estimate), so it runs in
body-cropped z-chunks: `CORE=260 OV=40` for the 0.94 mm NLM CT (7 chunks, 3.2 min each), `CORE=150 OV=30`
for the 0.72 mm Denver CT (12 chunks, 2.7 min each). Larger chunks die at the export step with
"Segmentation export worker died". The chunk cores are stitched back onto the full CT grid, so the
result shares the voxel frame of the TotalSegmentator and MOOSE outputs.

Orphaned model processes. When an nnU-Net worker is killed by the OOM killer, the Skellytour parent
process stays alive and keeps its RAM (about 1.6 GB each) and GPU memory. Before any new run:

```bash
ssh rub-pc 'pgrep -af "skellytour|moosez|TotalSegmentator|nnUNet" | grep -v pgrep; free -g; nvidia-smi --query-gpu=index,memory.used --format=csv'
# only if the listed processes belong to a finished or failed run:
ssh rub-pc 'pkill -f skellytour; pkill -f moosez; sleep 3; pgrep -af "skellytour|moosez" | grep -v pgrep; free -g'
```

Consensus of the three models and the laterality checks: `python scripts/ct-prior-consensus.py nlm` and
`... denver` (needs the copies listed above), outputs `generated/ct-prior-consensus-{nlm,denver}.json`
(agreement per named bone with a per-model status `present | negative | unsupported | unprocessed`; the
vertebra centroid block is diagnostic only; the laterality checks share TotalSegmentator organ labels and are
consistency checks, not independent tests). The merge with provenance was re-run on rub-pc on 2026-09-09
for both CTs (all chunks postprocessed, manifests complete): the stitched volumes are byte-identical to the
earlier ones (MD5 `cb3d6a9a…` NLM, `8efb1921…` Denver), so no downstream result changed; the new
`skellytour_high.json` manifests record per-chunk SHA-256 and seam agreement (Denver seam z 1500, cervical
spine, agrees on only 65 % of the doubly predicted voxels: boundary disagreement between chunks, identity
kept). Seams are also checked locally from the stitched volume with
`python scripts/skellytour-seam-check.py nlm|denver` (`generated/skellytour-seams-{nlm,denver}.json`:
label agreement at each seam against its neighbouring slices and the identity kept by every vertebra
label that crosses a seam).

Vertebra consensus by instance (names and counts observed, never imposed):
`python scripts/ct-vertebra-instances.py nlm --selftest` and `... denver --selftest` (about 5 min each,
8 GB RAM). The same script runs on the rib families: `... nlm ribs_left --selftest`, `... ribs_right`
(outputs `generated/ct-rib-instances-<ct>-<side>.json`, panels `generated/ct-rib-instances-<ct>-<side>/`,
label maps `rib-<side>-{instances,review,votes,eligible}.nii.gz`; no HRA chain, the HRA female skeleton has
no rib meshes). Outputs `generated/ct-vertebra-instances-{nlm,denver}.json` (candidates, pairwise
correspondence with states matched/split/merge/partial/unmatched, instance table with per-model state
`seed | matched | merge | partial | single | negative | absorbed | unsupported | unprocessed`, votes,
HRA same-donor chain by order, self-test results, per-instance `size_class`, `fragments`, `conflict_voxels`,
`lost_to_other_winner_ml` computed on the true per-model union), review panels in
`generated/ct-vertebra-instances-{nlm,denver}/` and the label maps `vertebra-{instances,review,votes,eligible}.nii.gz`
under `data/derived/nlm-vhf/consensus/` and `data/derived/denver/priors/consensus/`. The `--selftest` perturbs
one model's candidates (merge two bodies, split one, delete one, swap two names, shift one by 15 mm) and
must report the expected correspondence states; it covers only `correspondence()`. The procedure as a whole is
covered by `python scripts/test-ct-instances.py` (24 end-to-end scenarios on synthetic volumes through
`--inputs/--out/--no-panels/--no-hra`: baseline, label names permuted in every model, a model merging two
bodies, a model splitting one body, a missing body, a missing Skellytour chunk with and without
`--allow-incomplete`, near and far detached pieces, a small body seen by every model, contested boundaries
with per-model maps, and the anisotropic nearest-seed split). Run it after any change to the script.
Label maps written per run: `<stem>-{instances,review,votes,eligible}.nii.gz` plus `<stem>-model-<model>.nii.gz`
(the instance id each model votes, so every alternative can be rebuilt; `review` is a winner-takes-all view,
ties go to the lower instance index and never enter the consensus). Skellytour eligibility is read from the
merge manifest (completed chunk cores inside the crop); a manifest with `complete: false` stops the run unless
`--allow-incomplete` is given.
