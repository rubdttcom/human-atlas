# Reproduce the local atlas

Use Node 22.13+ and Python with the pinned packages in `requirements-pipeline.txt`.
The fork retains original source manifests and binary geometry alongside derived
atlas manifests. HRA binaries come from the pinned historical upstream revision.

```bash
npm ci
python3 -m venv .venv
.venv/bin/pip install -r requirements-pipeline.txt
.venv/bin/python scripts/fetch-tcia.py
.venv/bin/python scripts/ingest-tcia.py
node scripts/optimize-anatomy.mjs atlas-tcia-female.json tcia-003-lod
node scripts/compress-models.mjs atlas-tcia-female.json
.venv/bin/python scripts/fetch-denver.py
.venv/bin/python scripts/ingest-denver.py
node scripts/optimize-anatomy.mjs atlas-denver-female.json denver-vhf-lod
node scripts/compress-models.mjs atlas-denver-female.json
python3 scripts/build-registry.py
.venv/bin/python scripts/compose-female.py
```

The fetcher reads the ZIP central directory and downloads only subject 003 and
the official label key, validating ZIP CRCs. SHA-256 identities and the corrected
clinical metadata file are saved in `data/raw/tcia/download-manifest.json`.

The Denver fetcher opens `/usr/bin/google-chrome` (headed, display required) because
the Digital Commons download endpoint sits behind a Cloudflare JavaScript challenge
and returns HTTP 403 to plain HTTP clients. It downloads the "Final 3D STL Models"
and "Metadata" archives from inside the cleared page and writes
`data/raw/denver/download-manifest.json` with URL, size and SHA-256. The ingester
refuses an archive whose hash differs from that manifest, checks the archive README
licence text, verifies the axis convention and millimetre units from bone centroids,
welds each STL and records archive member, CRC and STL SHA-256 per mesh.

```bash
node scripts/validate-atlas.mjs
node scripts/validate-atlas.mjs atlas-female.json
node scripts/validate-atlas.mjs atlas-tcia-female.json
node scripts/validate-atlas.mjs atlas-denver-female.json
node scripts/validate-interactions.mjs
python3 scripts/validate-provenance.py
.venv/bin/python scripts/validate-composition.py
.venv/bin/python scripts/qa-geometry.py
./atlas check-licenses --target open-clean
./atlas check-licenses --target open-sharealike
./atlas check-licenses --target research-full
npm run check
npm run build
npm run dev -- --port 3017
```

In another terminal, run `.venv/bin/python scripts/browser-check.py`. The script
uses `/usr/bin/google-chrome` and writes screenshots and canvas-pixel evidence to
`artifacts/browser/`. GPU checks need a browser-capable environment.

To change individual composition choices, set source record IDs to boolean values
in `registry/composition-overrides.json`, then rerun composition and its verifier.
These overrides select geometry; they do not validate its registration.

The baseline composition recipe is per-system until reviewed crosswalks allow
finer automatic selection. Original source atlases preserve the excluded detail.
Neither counts nor licence eligibility imply anatomical correctness.
