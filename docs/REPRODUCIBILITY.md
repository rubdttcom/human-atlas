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

# Block C stage 0: origin completeness of the colour slices (reads the NLM 1996 INDEX and probes the server; nothing downloaded) and the trunk posture offset
.venv/bin/python scripts/check-cryosection-origin.py    # -> generated/cryosection-origin-check.json; --offline skips the HTTP HEAD probes
.venv/bin/python scripts/trunk-posture-offset.py        # ~70 s, 9 GB RSS; needs the consensus instance maps of BOTH CTs (nlm and denver); -> generated/trunk-posture-offset.json + .png
# The two ingests below read generated/trunk-posture-offset.json (posture_offset / trunk_posture_context in every trunk CT mesh): run it first.

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
.venv/bin/python scripts/validate-consensus-metadata.py   # model-agreement metadata of ct-consensus: source = manifest = composite = instance tables
.venv/bin/python scripts/test-consensus-metadata.py       # regression: corrupted gates / CT / Denver comparison fields in memory must fail the validator
node --experimental-strip-types scripts/test-agreement-panel.mjs   # viewer wording and null/zero/missing rendering of the agreement panel
.venv/bin/python scripts/ct-bone-consensus.py --selftest
.venv/bin/python scripts/ct-bone-consensus.py nlm        # about 4 min: gated per-name bone candidates (plan B 2.6), generated/ct-bone-consensus-nlm.json; nothing is composed
.venv/bin/python scripts/denver-ct-baseline.py            # about 5 min: Denver bones against the HU = 300 edge of the fresh CT (shape baseline), generated/denver-ct-baseline.json
python3 scripts/inventory-cryosections.py /media/rub/Backups/VHF/Female-Images --workers 12   # on rub-pc, about 2.5 min: SHA-256, decompressed size, planar RGB statistics, missing and placeholder slices -> fullbody-inventory.json (copied to generated/cryosection-inventory.json)
# Block C stage 0: alignment of the colour photographs against Denver's aligned slices (on rub-pc; env /media/rub/Backups/VHF/env has pydicom and scikit-image)
python3 scripts/check-cryosection-alignment.py --nlm /media/rub/Backups/VHF/Female-Images/fullbody --denver "/media/rub/Backups/VHF/denver/aligned-cryo/Aligned Cryosection-DICOM" --inventory /media/rub/Backups/VHF/Female-Images/fullbody-inventory.json --step 1 --workers 12 --window 8 --out cryosection-alignment-dense.json   # about 50 min, 22 GB RSS with 12 workers (per-worker photograph cache)
python3 scripts/check-cryosection-alignment.py ... --no-probe --refine-from cryosection-alignment-dense.json --out cryosection-alignment-final.json            # seeded third pass on the slices inconsistent with their neighbours, about 15 s; run once more with --compact to write the copy for generated/
#   full report (rotation grids, per-block rows) -> data/derived/nlm-vhf/cryosections/cryosection-alignment-full.json; compact copy -> generated/cryosection-alignment-check.json
.venv/bin/python scripts/build-cryosection-transform.py   # -> transforms/nlm-cryosection-to-vhf.json (three Denver blocks, per-slice table with identity status, extrapolation above the pelvis marked unverified); refuses partial or unresolved reports
# Block C stage 0: photograph-to-CT check (on rub-pc, about 4 min for every 5th photograph; Denver's aligned CT is the NLM fresh CT resampled, see PROGRESS)
python3 scripts/check-photo-ct-alignment.py --nlm .../fullbody --ct .../denver/aligned-ct-nii/denver_aligned_ct_hu.nii.gz --ct-transform denver-aligned-ct-voxel-to-vhf.json --transform nlm-cryosection-to-vhf.json --inventory fullbody-inventory.json --step 5 --workers 12 --out photo-ct-alignment.json   # -> generated/photo-ct-alignment-check.json; --rows-from re-summarises
# Block C stage 0: observability under the original labels at the block boundaries (on rub-pc; the label slabs come from VHF_Full.mat, see the script) and the quarantine
python3 scripts/cryosection-observability-band.py --nlm .../fullbody --slabs denver-label-slabs.npz --transform nlm-cryosection-to-vhf.json --out observability-band.json   # -> generated/cryosection-observability-band.json
.venv/bin/python scripts/build-cryosection-quarantine.py  # seed (registry/cryosection-quarantine-seed.json, reviewer findings) + band flags -> registry/cryosection-quarantine.json
.venv/bin/python scripts/select-cryosection-pairs.py      # quarantine first (excluded-observability, identity never overrides it), then policy pairs-v1 -> generated/cryosection-pair-selection.json (usable / usable-flagged / excluded-identity with ambiguity sets / blank); the RGB pilot reads this, never the transform's per-slice table directly
.venv/bin/python scripts/test-cryosection-transform.py    # in-memory corruptions of the report (truncated, missing/duplicated slice, unresolved status, photograph chosen twice) must be refused; identity status kept per slice
# Block C, RGB pilot steps 1 to 4 (roadmap 6b; plan B stage 2 inputs and stage 6 protocol). Nothing trained.
.venv/bin/python scripts/extract-denver-label-block.py --k-first 2285 --k-last 3532 --out data/derived/denver/label-blocks/block2-k2285-3532-labels.npz   # 3 s: byte copy of Denver original labels of block 2 + names + mat SHA-256 (no h5py needed downstream)
python3 scripts/build-cryosection-rgb-block.py --nlm .../fullbody --denver ".../denver/aligned-cryo/Aligned Cryosection-DICOM" --transform nlm-cryosection-to-vhf.json --pairs cryosection-pair-selection.json --labels block2-k2285-3532-labels.npz --region 2 --out out --workers 12   # on rub-pc, 28 s: rgb-kji.npy (1.08 GB), denver-original-labels.nii.gz, manifest.json (hash of every photograph, NCC check against Denver gray, mirror control); copy out/ to data/derived/nlm-vhf/cryosections/block2/ and manifest.json to generated/cryosection-rgb-block2-manifest.json
.venv/bin/python scripts/build-cryo-tissue-map.py            # -> registry/cryo-tissue-map.json v1 (131 Denver values -> tissue class; precedence, body-mask rule)
.venv/bin/python scripts/build-cryo-tissue-classes.py --block data/derived/nlm-vhf/cryosections/block2 --selftest   # 20 s: tissue-classes.nii.gz (ignore 255 inside the body and on excluded slices) + generated/cryo-tissue-classes-block2.json
.venv/bin/python scripts/select-cryo-eval-bands.py           # -> registry/cryo-eval-bands-v1.json: two seeded 50 mm bands with 10 mm buffers, frozen to the manifest, map and label-slab hashes; deterministic (seed 20260913)
.venv/bin/python scripts/test-cryo-metrics.py                # 25 synthetic cases of the frozen pilot metrics (scripts/cryo_metrics.py: Dice under eligibility, symmetric pooled voxel-surface p95 per k-run, caps removed on both sides, emptiness before caps, tolerance)
.venv/bin/python scripts/test-denver-rasteriser.py           # 6 analytic cases of the even-odd rasteriser (one box, disjoint, nested hole, overlap = XOR by convention, open contour refused)
.venv/bin/python scripts/denver-surface-floor.py             # about 10 min, 25 GB RSS: Denver original labels vs final meshes voxelised (even-odd fill; the noise-floor rasteriser dropped multi-contour slices) scored with cryo_metrics -> generated/denver-surface-floor.json (H_vox, P_vox per class: the protocol thresholds)
.venv/bin/python scripts/cryo-pilot-evaluate.py --block data/derived/nlm-vhf/cryosections/block2 --oracle   # about 13 min: prediction := reference (gates: registry validator, identity chain, grid, training provenance); freezes the evaluator sanity figures -> generated/cryo-pilot-oracle-controls-block2.json
#   registry/machine-acceptance-protocol-v1.json is written by hand before training (plan B 2.7; revised after the Codex audit of afec927, before any training); hashes and thresholds are checked by the validator
.venv/bin/python scripts/validate-cryo-pilot.py              # manifest rows = transform rows and inventory hashes, map names = source names, bands and training eligibility reproduce, protocol thresholds = surface floor, hash chain
.venv/bin/python scripts/test-cryo-pilot-validator.py        # 27 in-memory corruptions (wrong n / tc / hash / name / band / threshold / eligibility) must each fail the validator
.venv/bin/python scripts/test-cryo-pilot-evaluator.py        # about 1 min: gate cases of the evaluator (translated affine, int16 256.., float, foreign label, foreign block, missing or contaminated training manifest) must each be refused before scoring
.venv/bin/python scripts/ct-candidate-shape-check.py nlm  # about 1 min: the same procedure on the shipped bone candidates; writes generated/ct-candidate-shape-check-nlm.json and shape_check into the bone report; re-run ingest afterwards
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

## Model agreement of the consensus instances

`scripts/ingest-ct-consensus.py` copies the per-instance vote figures of
`generated/ct-vertebra-instances-nlm.json` and `generated/ct-rib-instances-nlm-{left,right}.json`
into the provenance of every `ct-consensus` mesh (`consensus_ml`, `union_ml`, `agreement_ratio`,
`unanimous_fraction`, `eligible_models_on_consensus`, `votes_histogram_on_union`,
`conflict_voxels`, `lost_to_other_winner_ml`, `models`, `source_labels`, `candidate_name`,
`name_status`). `build-registry.py` carries them into `manifests/ct-consensus.json` and
`compose-female.py` into the composite unchanged (they describe the CT grid, registration does
not alter them). The viewer renders them in the "Model agreement (CT consensus)" panel
(`app/agreement.ts`, `app/provenance.tsx`) with every denominator spelled out: agreement ratio =
consensus / union voxels; unanimous fraction over consensus voxels; the state of each model, where
`unsupported` (no class), `unprocessed` (outside the model's processed region) and `absorbed`
(another label of that model) are shown apart from `negative`. The wording is agreement between
models, never probability of correctness, anatomical confidence or independent validation, and
the candidate name stays `pending`. `validate-consensus-metadata.py` fails if any copy drifts,
any figure contradicts the instance table or its own totals, a state leaves the documented
vocabulary, a name status changes, or a review-only instance gets meshed.

## Per-name bone candidates (plan B section 2.6)

`scripts/ct-bone-consensus.py nlm` reads `registry/ct-label-equivalence.json` (class equivalence
between the TotalSegmentator, MOOSE and Skellytour vocabularies, with evidence; group labels never
meet individual bones) and, per class, applies the four gates before any vote: geometric
correspondence of the largest components (IoU >= 0.50, centroid <= 15 mm per pair), laterality
(anchored by the organ test of `ct-prior-consensus.py`), coverage and eligibility (Skellytour
crop, class support, contact with the CT field-of-view edge). The vote and its figures are those
of the instance tables, so the viewer panel and `validate-consensus-metadata.py` apply unchanged
if a candidate is ever ingested. Every result is a candidate with `review_status:
machine-unverified`: `candidate-consensus`, `candidate-single-model` (MOOSE-only bones and groups,
whose agreement figures are undefined, not perfect), `disputed`, `laterality-failed` or
`not-accepted`. The report compares each candidate with the current TotalSegmentator label of
`nlm-vhf-ct` (Dice, volume ratio) and, where a Denver mesh exists, with that mesh (surface-to-vertex
distances in the canonical stage, both directions). No candidate replaces anything in the
composite; substitution is a separate recorded decision per bone (plan B section 2.6). Label maps:
`data/derived/nlm-vhf/consensus/bone-consensus.nii.gz` and `bone-single-model.nii.gz`.

Since 2026-09-12 night `ingest-ct-consensus.py` also meshes the `candidate-consensus` bones as a
fourth family (`bones`, ids `CTCONS:VHF:B01..`) of source `ct-consensus`: same vote fields,
plus `gates`, `consensus_status`, `review_status: machine-unverified`, the comparison with the
`nlm-vhf-ct` label and with the Denver mesh, and `name_status: pending`. Their structure id is
the one the reviewed crosswalk gives the shared TotalSegmentator label, so each candidate is an
alternative of the same catalogue entry as the `nlm-vhf-ct` label and the Denver mesh (viewer
side-by-side comparison); machine-unverified records never become `best_available` ahead of a
source of equal priority, `compose-female.py` never composes them, and `validate-composition.py`
and `validate-consensus-metadata.py` fail if they are composed, if a gate did not pass, or if the
comparison is missing. Since 2026-09-12 (audit finding on f28467f) the validator also compares
`gates`, `versus_nlm_vhf_ct_label`, `versus_denver_mesh`, `denver_mesh`, `bone_class`,
`review_status` and `consensus_status` field by field between the bone report, the source atlas and
the manifest, checks the gate records internally (one passed pair per pair of voting models,
class-equivalent voting models, per-model side equal to the expected side, coverage figures in
range), requires the CT-label comparison for every candidate and the Denver comparison for every
candidate with a Denver mesh (p50 <= p95, note stating it is not a substitution decision);
`scripts/test-consensus-metadata.py` corrupts those fields in memory and expects the validator to fail.

Shape check (plan B section 2.6, 13 September 2026): `scripts/ct_edge_fit.py` holds the one procedure
(HU = 300 iso-surface of the fresh CT inside a 20 mm band, coverage mask, placement residual as
registered, own rigid ICP anchored at the centroid in 8 mm then 4 mm bands, divergence at 15 deg or
15 mm). `denver-ct-baseline.py` runs it on the 28 Denver bones (figures unchanged by the refactor) and
`ct-candidate-shape-check.py nlm` on the shipped candidate meshes, binding each result to the
`geometry_sha256` of the mesh. The criterion is shape p95 <= the Denver bone of the same class and
side; classes Denver does not cover get `no-class-baseline` and no acceptance. Order:
`ct-bone-consensus.py nlm` -> `ingest` -> `optimize` (the shipped mesh must exist) ->
`ct-candidate-shape-check.py nlm` -> `ingest` again (copies `shape_check` into the provenance) ->
`optimize` -> `build-registry` -> `compose` -> QA -> `build-registry` -> validators;
`validate-consensus-metadata.py` requires `shape_check` on every candidate, checks the digest against
the shipped buffer and the baseline figure against `generated/denver-ct-baseline.json`. A candidate
is segmented on the same CT it is compared with, so a small residual measures the label boundary
against the HU threshold, not independent geometry. Not-accepted and single-model candidates are listed in
`review_only_bone_candidates` of the atlas and are not meshed. Order after the batch:
`ct-bone-consensus.py nlm` -> `ingest-ct-consensus.py` -> `optimize-anatomy.mjs atlas-ct-consensus.json ct-consensus-lod`
-> `build-registry.py` -> `compose-female.py` -> QA passes -> `build-registry.py` -> validators.
