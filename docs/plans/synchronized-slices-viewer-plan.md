# Synchronized 3D and slice viewer: implementation specification

Status: implementation started at the user's subsequent request. First-release scope remains phases 0–4; phase 5 is separate. Phase 0 decisions and frozen tolerances are in [synchronized-slices-decisions.md](synchronized-slices-decisions.md). This work does not start training or authorize deployment. Repository working agreement and data rules continue to apply.

## 1. Purpose and reference

Add a **Slices** mode to the existing atlas that teaches the relationship between a complete 3D structure and its appearance in a section of the original image volume. A shared position and plane orientation must drive both the 2D image and the plane displayed in 3D.

Reference: [28-second viewer demonstration](https://omarchy.tail5b3a99.ts.net:8444/video/video.mp4), supplied by the user. Six sampled frames were inspected on 13 September 2026. The reference shows an orthogonal four-panel layout, organ selection, and an oblique two-panel layout with position, angle and window controls. This is a behavioral reference, not evidence of its implementation stack; the private URL may not remain available. Do not copy its code or assets.

## 2. Scope and delivery boundary

First release: an abdominal region of the existing NLM VHF fresh CT, its original segmentations and its corresponding CT-derived meshes. Deliver all three orthogonal views and an oblique view. Use existing organ labels where present: liver, spleen, stomach, left/right kidneys, aorta and inferior vena cava. Spine context may use registered CT consensus instances with explicit mapping to their own masks and pending names; it must not silently map instances to TotalSegmentator vertebral names.

The initial CT experience does not depend on completion of cryosection model training. A subsequent release can reuse the interaction for RGB cryosections, starting with the prepared block 2.

Not included in the first release: segmentation inference, arbitrary user DICOM uploads, diagnostic tools, anatomy quizzes, full-body high-resolution streaming, new registrations, editing masks, changing the composite recipe, or automatic substitution of candidate meshes.

## 3. Existing foundation and missing pieces

- `app/page.tsx`: source choice, search, structure selection, visibility and inspector state.
- `app/scene.tsx`: Three.js rendering, picking, selection highlights, camera controls and registration landmarks. Rendering uses merged geometry and per-part shader state; a new plane must coexist with that mechanism.
- `app/anatomy.ts`: atlas and scene contracts; preserve the existing atlas experience.
- `scripts/ingest-nlm-vhf.py`: records the CT voxel-to-stage chain used for the meshes.
- `transforms/canonical-space.json`, `transforms/source-to-stage.json` and `transforms/nlm-ct-to-vhf.json`: recorded spatial transforms.
- Local derived CT volumes, segmentation masks and `data/derived/nlm-vhf/ct-coverage-mask.nii.gz` are available outside Git. Exact input paths and hashes must be resolved when implementation begins.
- `data/derived/nlm-vhf/cryosections/block2/`: prepared RGB array, labels and manifest for the later extension.

Missing: a browser volume package, scalar/RGB volume sampling, label overlays, synchronized slice state, plane rendering and the slice workspace UI. Existing mesh `.bin` files contain surfaces, not CT intensities.

## 4. User experience

### 4.1 Entry and source selection

Add Atlas / Slices mode selection. Entering Slices selects a compatible volume with its corresponding source structures. Explain the source transition when entering from the composite or another source. Preserve the previous atlas state for exit.

The initial view centers the configured abdominal region, with soft-tissue window W=400 / L=50 as a starting display preset. Exact presets are display settings, not interpretation guidance. Show source, current image resolution and attribution. The active region must have explicit bounds in the volume manifest.

### 4.2 Orthogonal workspace

Desktop: four panels, 3D upper left, axial upper right, coronal lower left and sagittal lower right. Every CT panel shows orientation labels, crosshairs, a slice-position readout and the selected structure's overlay if a corresponding mask is available.

- Clicking or dragging in a CT panel changes the shared physical position in that panel; the other views and the 3D planes update together.
- Wheel navigation moves through slices along the active panel normal; provide sliders and keyboard equivalents.
- Orbiting the 3D camera changes only the camera, not the sampling plane.
- Selecting an organ in 3D or in the list shares selection with every slice. Selecting a labeled pixel can select its mapped structure; unlabeled pixels must not invent a structure.
- Provide separate actions to select and to center on a structure, so selection does not unexpectedly move the current slice.
- Plane visibility and overlay opacity are independent controls. Selected structures remain identifiable with surrounding anatomy visible.

Use a scoped input focus policy so scrolling a sidebar does not move a slice. Provide labeled controls and visible focus. On narrow screens, keep 3D plus one active slice visible or allow explicit panel switching; preserve the same shared state.

### 4.3 Oblique workspace

Two panels: 3D with the sampled plane and one oblique reconstructed image. Start from the current axial plane through the shared crosshair. Controls: translation along the plane normal, two inclination angles, reset orientation, window width/level and overlay opacity.

Freeze the angle convention in code and documentation: rotations about the initial in-plane axes, with a defined order, in degrees. Rotations pivot around the shared crosshair. Translation changes that crosshair along the current normal. Returning to orthogonal mode retains the resulting physical point and orthogonal anatomical axes. The plane's displayed texture and the 2D image use identical sampling coordinates.

Oblique edge labels must represent the actual directions projected onto the plane, including mixed directions where appropriate; do not label an arbitrary tilted view as if it were axial.

### 4.4 Image and selection controls

Window width must remain positive. Supply soft-tissue and bone display presets, reset, and independent zoom/pan per 2D panel. The default overlay is the selected structure's boundary, with an optional translucent fill. Use the same structure color in 2D and 3D.

Disable exploded geometry while in Slices: displaced organs no longer occupy the sampled coordinates. Missing masks produce an explicit unavailable-overlay state, not a fabricated contour from an unrelated source. Mesh smoothing and decimation can make mesh boundaries differ from original masks; overlays represent masks and must say so in source details.

## 5. Data package and provenance contract

Build a reproducible, read-only derivative of the existing inputs, initially cropped to the abdomen and downsampled for interactive display. Do not overwrite source volumes, model outputs, frozen pilot artifacts or QA registries. Proposed builder: `scripts/build-viewer-volume.py`; proposed outputs: an ignored derived package, copied to a configured static asset location only for serving. Decide hosting and Git policy before adding generated binaries to `public/`.

Each versioned manifest must contain:

- Dataset/donor/modality identifiers, source paths or identifiers and SHA-256 hashes, builder version and parameters, licence and mandatory attribution.
- Dimensions, explicit axis/storage order, scalar type, byte order, channel order, compression and per-chunk URL, dimensions and digest.
- Physical units, voxel-center convention, voxel-to-source-physical and voxel-to-canonical-stage matrices, with transform identities and hashes. Include crop and resampling in the output affine.
- Intensity scale/intercept and units (HU for CT), valid range and initial display window. Never apply the HU conversion twice.
- Levels of detail with their spacing, affines, crop bounds and estimated decoded memory; do not describe a preview as native resolution.
- Coverage/support mask with separate states for acquired data, outside coverage and unavailable chunks. For RGB, preserve excluded/unknown slices separately from black or background.
- Explicit label-value to source-structure-id mapping, mask grid metadata and hashes, selected mesh identifiers and their existing geometry identities. Never join labels and meshes by display name alone.
- Provenance, name, placement and machine-review states as separate fields or referenced records; rendering grants no new status.

CT intensities use linear interpolation; categorical labels use nearest-neighbor sampling. Use sufficient halo voxels at chunk boundaries for continuous intensity sampling. Missing data must remain visible as unavailable; never interpolate across unsupported gaps. Define a conservative support rule for samples whose interpolation footprint touches invalid voxels.

First benchmark a single modest preview volume. Use chunked region loading and a bounded cache for finer resolution when measurements justify it. Progressive loading must not combine labels and CT from mismatched grids or package versions.

## 6. Coordinate and rendering design

Keep the existing React + Three.js foundation. Isolate volume loading and sampling from UI state; do not introduce a second rendering framework without a measured need. GPU volume textures/shaders are the proposed fast path, subject to device capability checks and a small prototype. Exact texture formats and compression support must be checked against the installed Three.js version at implementation time.

Use the canonical stage as shared interaction space. Its documented axes are +x subject left, +y superior, +z anterior, in metres. Image affines can use different directions and millimetres; never infer them from array indices.

For output pixel coordinates `(u, v)` measured in physical plane units:

```text
stagePoint = planeOrigin + u * planeRight + v * planeUp
volumePoint = inverse(voxelToStage) * stagePoint
imagePixel = sample(volume, volumePoint)
labelPixel = nearestSample(labels, inverse(labelVoxelToStage) * stagePoint)
```

Plane basis vectors are orthonormal and expressed in the same units as the origin. Pixel centers and physical aspect ratio must be explicit. All panels and the 3D plane consume the same plane descriptors, avoiding duplicated sign, rotation and offset logic. The original CT acquisition axes define the initial orthogonal views; transform those bases into stage space rather than assuming stage axes are the CT axes.

Suggested modules, names provisional:

- `app/slices/types.ts`: package, shared position, selection and plane contracts.
- `app/slices/coordinates.ts`: pure transforms, plane bases, bounds and direction labels.
- `app/slices/volume-loader.ts`: loading, decoding, cancellation, cache and integrity errors.
- `app/slices/sampler.ts` and shader resources: CPU reference sampler and GPU path.
- `app/slices/slice-panel.tsx`: image, crosshair, zoom/pan and input mapping.
- `app/slices/workspace.tsx`: layout, controls, source switching and shared state.
- A small `app/scene.tsx` extension to attach/update/dispose planes and accept the workspace viewport.

Render on changes, coalesce pointer events per animation frame, and move expensive decoding out of the input/render path. Define texture ownership: dispose resources on source change and exit; cancel stale requests; reject late responses from a previous volume. Handle WebGL context loss and unsupported volume sizes with a clear retry or lower-resolution path.

## 7. Dataset compatibility and RGB extension

The initial default is CT plus its CT-derived structures. The composite includes Denver geometry and an HRA reference assembly; same-donor provenance alone does not establish matching acquisition posture. Do not show all composite structures as if they were segmentations of this CT. Any future comparison overlay needs explicit source and placement context.

For RGB, use the prepared block's own manifest, spatial mapping, support and eligible labels. Show source photographs on native section planes; describe coronal, sagittal and oblique RGB images as reconstructions. Define color-space handling for interpolation and verify it against native slices before shipping.

Preserve identity exclusions, observability quarantine and missing slices. Never bridge a block gap or excluded slice with apparently observed anatomy. Tissue-class masks (bone/muscle/cartilage) must not be presented as organ-instance labels. Original Denver structure labels and future machine candidates keep their separate identities and statuses.

The documented photograph-to-CT discrepancy grows to about 42 mm at the head under the current placements. Upper-body photograph mapping remains `extrapolated-unverified`. Simultaneous CT/RGB correspondence beyond supported regions needs its own registration protocol; this viewer plan does not supply or authorize that correction. RGB rollout can begin within the supported prepared block without claiming whole-body alignment.

## 8. Implementation phases

| Phase | Deliverable | Exit condition |
| --- | --- | --- |
| 0: inputs and coordinates | Resolve abdominal bounds, exact CT/mask/mesh identities, display orientations and baseline hardware; tiny synthetic asymmetric phantom | Affines, label joins, coverage semantics and test tolerances documented before UI work |
| 1: volume preparation | Reproducible preview package, manifest, support mask and loader | Native reference slices reproduce; malformed metadata and incomplete chunks fail visibly; memory measured |
| 2: orthogonal mode | Four panels, shared crosshair, three 3D planes, selection overlays, window controls | Pointer/keyboard navigation stays synchronized; source entry/exit preserves atlas behavior |
| 3: oblique mode | Shared oblique sampling and textured 3D plane; two angles and normal displacement | Arbitrary planes match an independent CPU sampler within frozen numeric tolerances |
| 4: release checks | Adaptive resolution/cache where needed, responsive controls, provenance and error states | Functional, coordinate, browser and performance checks pass; limitations recorded |
| 5: RGB extension | Prepared cryosection block, color reconstruction and supported masks | Source images reproduce, gap/quarantine handling passes, no implied CT/RGB registration or organ labels |

Phases 0–4 define the first release; phase 5 is separate. Record measured timings after phase 1 before estimating the remainder. No calendar commitment is implied by this deferred plan.

## 9. Acceptance and verification

Technical checks establish software behavior, not anatomical accuracy. Freeze numeric sampling tolerances in phase 0 with the chosen storage precision; do not relax them to match later failures.

1. **Spatial correctness:** asymmetric phantom with known left/right markers, anisotropic spacing, translated/rotated affine and nonzero crop offset. Voxel → stage → voxel round trips meet a proposed tolerance of 1e-4 voxel in CPU math. Test every plane and radiological display convention; a mirror control must fail.
2. **Sampling correctness:** compare output against an independent CPU reconstruction for native, orthogonal and tilted slices. Integer voxel centers reproduce stored CT values and mask ids; interpolation errors meet the frozen numeric tolerance. Test HU conversion, nearest-label sampling and boundary support explicitly.
3. **Synchronization:** known pixel picks map to the same physical point in all panels; the 3D plane agrees within half an output pixel in physical distance. Oblique zero angles reproduce axial sampling. Rotation preserves the pivot and translation follows the normal.
4. **Identity and gaps:** wrong label map, wrong affine, incompatible mesh/source ids, stale request, missing chunk and unsupported sample all produce explicit states. No interpolation through excluded slices and no label overlay from another source.
5. **Browser behavior:** inspect a real abdominal package in the supported browsers, including organ selection, crosshair drag, wheel/keyboard controls, resize, source switches, oblique reset, loading errors and exit. Verify that Atlas selection, isolation and provenance panels still work.
6. **Performance:** provisional target after data load is p95 input-to-display latency below 100 ms and at least 30 fps during continuous plane dragging on a recorded desktop/browser/preview size. Record GPU/CPU memory, network bytes and initial load time; select concrete resource budgets in phase 0. Repeated entry/source-switch/exit cycles must not show monotonic retained-resource growth. Offer reduced resolution when the target is unsupported.
7. **Project checks:** run `npx tsc --noEmit`, `node --experimental-strip-types scripts/test-agreement-panel.mjs`, focused new coordinate/sampling tests and a production build for viewer changes. A data builder or other script change also requires the applicable full definition-of-done checks in `CLAUDE.md` and `docs/REPRODUCIBILITY.md`. Geometry/label/registration changes, if separately authorized, require their full pipeline.

Record the examined revision, actual tests, benchmark environment and limits in `docs/PROGRESS.md`. Do not use “validated” for anatomy, meshes, names or placement. No commit, push or deployment without the user's corresponding instruction.

## 10. Decisions to resolve when work starts

- Exact abdominal extent and preview spacing, based on source coverage and memory measurement.
- Static volume hosting, maximum asset size, packaging/compression and browser support matrix.
- Whether CT consensus spine context belongs in the first release or a later increment; default organ overlays can ship without it.
- Overlay policy for simultaneous selection of multiple structures; start with one active structure and retain existing atlas selection on exit.
- Concrete loading/resource budgets and numerical tolerances for the chosen GPU format.

These are implementation decisions for the future task, not blockers for the current cryosection work.
