# Slices phase 0 decisions (2026-09-13)

Implementation requested by the user; the first release is phases 0–4 of
`synchronized-slices-viewer-plan.md`. RGB remains a separate release. No training,
source edits, geometry rebuild, commit or deployment is part of this work.

## Inputs and crop

The three inputs have shape 512 × 512 × 1734 and the same affine in RAS mm:
diagonal (-0.9375, -0.9375, -1), translation (239.53125, 239.53125, 0).
CT is int16, slope 1, intercept 0: values already represent HU. Masks and support
are uint8. Retained voxel centres must reproduce input values without a second HU conversion.

| Input under `data/derived/nlm-vhf/` | SHA-256 |
| --- | --- |
| `vhf-fresh-ct.nii.gz` | `5284a87267a83911f0174a07fb3f755301376eb5658daf12d95455cc2ecad26f` |
| `totalseg.nii` | `e52951d0589e325a65932483e19e6bb09556a1ca4feb7e2265c5f25199271177` |
| `ct-coverage-mask.nii.gz` | `9d3c934e33af5c3f26be10feb7cee34b9fdcc4665a0205e3ad2c70ec13442ca6` |
| `totalseg-classmap.json` | `136a745ddb9e1aa2113fb101b8ddb9105fadf4c85946b138e5ca61cd54f2c0d9` |

Choose input crop [0,512) × [0,512) × [408,720), with preview stride 3 in
each axis (171 × 171 × 104; 2.8125 × 2.8125 × 3 mm). This includes the full
measured extents of liver, spleen, stomach and kidneys with axial margin; the
aorta is intentionally cropped (its label extends to slice 321). Keep the whole
in-plane acquisition field. Initial point is the crop centre. Preview is decimated,
not native resolution; tiny labels may disappear at this spacing.

Map values 1, 2, 3, 5, 6, 52, 63 to source assets `NLMCT:VHF:` followed by
`spleen`, `kidney_right`, `kidney_left`, `liver`, `stomach`, `aorta`,
`inferior_vena_cava`, respectively. Verify each value against `source_metadata`
and bind to the geometry identity in `public/atlases/nlm-vhf-ct.json` provenance.
No name-based join, consensus vertebrae or composite geometry in this release.
Mask boundaries describe original model labels; mesh component removal, smoothing
and decimation can produce differences. Existing provenance and review states stay separate.

## Coordinate and numerical contract (frozen before UI)

Stage metres follow voxel → original CT RAS mm → `nlm-ct-to-vhf` →
`denver-image-to-stage`. Output affine includes the crop translation and stride.
All matrices are row-major; integer indices are voxel centres; disk arrays are
little endian with x fastest. Initial view bases come from acquisition columns:
axial right +i/up -j, coronal right +i/up -k, sagittal right +j/up -k. Normal is
right cross up. Sheared grids are refused. Initial radiological display places
subject left at image right. Direction labels use actual stage components;
components with magnitude at least 0.2 appear, largest first.

Oblique angles in degrees are extrinsic Rodrigues rotations: first about initial
axial right, then about initial axial up. Origin is unchanged. Normal translation
moves that shared origin. Pixels sample their centres; canvas y increases down.

Frozen tolerances: CPU round trip ≤ 1e-4 voxel; HU reconstruction ≤ 1e-3 HU
against an independent analytic oracle; future GPU float32 reconstruction ≤ 0.1 HU;
categorical labels exact away from nearest-neighbour ties; 3D/2D plane distance
≤ half an output pixel. These must not be loosened after observing failures.
At a nearest-neighbour tie, choose the larger index (`floor(x + 0.5)`).
Every nonzero interpolation weight requires support at its voxel. Downsampling
must also preserve gaps between retained input samples conservatively. Missing
chunks are unavailable, never background or outside acquisition. Values within
1e-7 voxel of the outermost centre are clamped solely for affine round-off.

The asymmetric synthetic test has anisotropic spacing, nonzero crop, rotation,
translation, distinct lateral labels, and a scalar ramp (-1000 + 13i + 29j + 71k).
Its independent analytical oracle and deliberate mirror control must pass before UI.

## Serving and performance decisions

Keep packages in ignored `data/derived/viewer/`; static serving copies go to
ignored `public/volumes/`. No generated volume binaries enter Git. One uncompressed
preview level first: float32 HU + uint8 labels + uint8 support, about 17.4 MiB
decoded. Single package ceiling 32 MiB, volume CPU retained budget 64 MiB,
GPU volume budget 64 MiB (excluding existing meshes). Finer chunks/cache are
conditional on measured need, not a prerequisite for this modest preview.
Reduced sampling resolution must be offered if frame performance is insufficient.

Baseline available here: Linux x86_64, AMD Ryzen AI 9 365 with Radeon 880M,
20 logical CPUs, Node 22.22.2, installed Three.js 0.159 series. Actual browser,
renderer, memory, network and timing observations still need recording. Target
desktop Chromium and Firefox; report actual tested engines and limitations.
After load: p95 input-to-display <100 ms and ≥30 fps continuous dragging.
GPU format/capability prototype and real-package benchmark are still pending;
the current CPU implementation is the reference sampler, not a performance claim.

## Phase 1 observations

`scripts/build-viewer-volume.py --serve` produced the real package on 2026-09-13:
18,246,384 decoded bytes (17.40 MiB), 171 × 171 × 104. Initial measured build
3.327 s; repeat 2.796 s internally / 3.07 s process wall time, peak builder RSS
1,437,344 KiB (`/usr/bin/time -v`, baseline hardware above, warm filesystem).
That peak is offline Python preparation, not browser memory. Uncompressed static
buffer bytes equal decoded bytes; manifest and source atlas add their own transfer.
No browser load time, GPU allocation or interaction benchmark has been measured yet.

The real-data test compares all 3,041,064 retained CT values and all corresponding
label values exactly against original NIfTI slices, checks crop-to-stage landmarks,
and rebuilds twice to require identical manifest hashes. The synthetic gap test puts
an unsupported voxel between retained centres and requires the affected cells to be
unsupported. The source coverage's <= -999 HU air/padding exclusion is documented
in the manifest; support is conservative rather than a promise that every acquired
air voxel is displayed.

Loader tests pass real-package loading, 24 metadata/identity/grid mutations, missing,
truncated and modified chunks, changed source atlas, aborted loads and superseded
responses from a server ignoring cancellation. The loader binds the served atlas hash,
input identities, cropped affines, exact provenance and geometry identities before
returning a volume. No global volume cache is retained. Phase 2 now connects this
package to the workspace; timing estimates for UI completion remain uncommitted.
