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

## Workspace implementation observations (2026-09-14)

The workspace now supplies Atlas/Slices entry/exit, orthogonal four-panel and
oblique two-panel layouts, shared position and selection, explicit centring,
window presets, mask boundary/fill opacity, plane visibility, independent pan/zoom,
keyboard/wheel/drag input, reduced display resolution and mobile panel switching.
It restricts 3D geometry to the seven mapped original CT assets and their used
chunks, checks mesh buffer hashes, and preserves Atlas React state on return.
The heading and source details identify these seven slice-compatible parts; the
structure selector contains only that exact label-to-mesh mapping.
The 3D scene consumes the actual copied slice canvases and their plane descriptors.
It disposes plane textures and releases its graphics context on exit. Detailed
retained-resource accounting remains to be measured.

One `SliceRenderEngine` owns three `Data3DTexture`s: R32F HU, R8 labels, R8 support,
nearest texture filtering with explicit trilinear scalar sampling in GLSL3.
Support values 0/1 in normalized R8 must be compared against 0.5/255, not 0.5;
the first screenshot exposed that bug, now corrected. Labels decode by ×255 and
rounding. GPU float readback is a test-only method, not a product control.

Real-package comparison against the CPU reference passed 20,173 supported samples
across axial, coronal, sagittal and two oblique orientations: maximum error
0.005530598 HU (frozen limit 0.1 HU), zero support or label mismatches.
The first run found 25 support disagreements: affine inversion made exact native
centres such as k=51 become 50.99999999999994 in CPU double math, introducing a
spurious nonzero interpolation weight into the excluded neighbour. `sampleStage`
now removes inversion round-off within 1e-10 voxel of integer centres;
`sampleVoxel` still rejects every genuinely nonzero unsupported contribution,
including the new 1e-8-voxel control. Numeric acceptance tolerances are unchanged.

`scripts/browser-check-slices.py` uses Chromium 143.0.7499.4, ANGLE SwiftShader
on CPU, at 1440×1000 and 390×844. It passes source loading, native/shader sampling,
selection without centring, explicit centring, keyboard, wheel, width clamping,
oblique pivot/reset, reduced resolution, exit, and no horizontal overflow.
Added checks cover repeated picks at the same pixel, sidebar wheel isolation and
orbit leaving both the crosshair and slice image unchanged. That repeated-pick
test guards a UI correction: the raster centre is now the fixed volume centre
projected onto the shared plane, so moving the crosshair within a slice does not
drag its image underneath the cursor.

The headless harness must omit inherited DISPLAY/WAYLAND_DISPLAY/XAUTHORITY;
otherwise ANGLE attempts an authenticated X11 connection and fails. Chrome 149
with native EGL was separately observed to expose the Radeon 880M, but no native
performance benchmark was run. After the user's restriction on GPU work, all
browser shader checks use SwiftShader CPU only. No training folders are accessed.
Browser reports/screenshots are in ignored `artifacts/slices/`. These checks are
not the complete release acceptance suite: remaining gates are recorded below.

## Remaining first-release acceptance gates

- Complete the remaining interaction and production checks below. The synthetic
  shader and recovery checks recorded in the following section now pass.
- Inspect Atlas selection/isolation/provenance restoration, actual network/load
  time, CPU/GPU allocation budgets and repeated entry/exit retained resources.
- Production Chromium and Firefox regressions now pass the tested interactions;
  sustained hardware performance and resource budgets remain open. Do not claim a
  browser supported solely from the Chromium result.
- Complete the requirement-by-requirement release audit and applicable repository
  checks on the final state. RGB remains phase 5, outside this first release.

## CPU browser follow-up (2026-09-14, working tree based on 4f4c825)

The asymmetric shader phantom now passes in Chromium 143 and Firefox 155:
315 native centres, 720 orthogonal/tilted samples, maximum error
0.0001189248 HU, mirror negative control, excluded-gap controls, and zero retained
volume textures after disposal. Real-volume shader/reference comparison passes
20,173 supported samples with maximum error 0.0055305978 HU and no label/support
mismatches. Chromium also passes missing-intensity-chunk error/retry and actual
3D context-loss error/retry. The browser regression selects a mapped organ by
clicking the 3D canvas, verifies pan/overlay/plane controls and switches the
active mobile panel.

Firefox uses a private Xvfb display and Mesa llvmpipe, with software rendering
checked before opening the atlas. It passes desktop/mobile interaction checks.
Its resize test exposed immutable texture storage being reused after canvas
dimensions changed. The scene now replaces and disposes that CanvasTexture;
the repeated Firefox run passes without texSubImage errors.

The sustained Chromium **software** benchmark on the production build still fails
the performance target: with the renderer's software-adaptive 0.5 pixel ratio,
384-pixel slices give p95 335.2 ms and 10.64 fps; 192-pixel slices give p95
278.2 ms and 12.05 fps. These are not hardware-GPU measurements or a release pass.
The adaptive path preserves full-resolution slice canvases and lowers only the 3D
context density; hardware renderers retain the existing 1.5–2× density path.
Input-to-display timing observes a coherent displayed set of planes and the next
animation frame, including input/render scheduling. Performance measures are
cleared after delivery to observers. The eight-cycle production run records six
volume/mesh resources, 26.85 MB transferred and 26.89 MB decoded; the slowest
resource took 601 ms. Backing storage stays near 33.41 MB while JS heap rises from
11.04 to 11.35 MB and embedder heap from 2.36 to 3.15 MB. This does not establish
the absence of retained-resource growth; the hardware performance measurement and
a longer lifecycle audit remain open.
