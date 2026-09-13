# Working agreement for agents on the Female Open Human Atlas

Read by Claude Code (`CLAUDE.md`) and Codex (`AGENTS.md`, a symlink to this file). Keep it short; the
detail lives in the documents it points to. Repository docs are written in English; talk to the user in
Spanish.

## Where the truth is

1. `docs/PROGRESS.md`: authoritative state and the "what remains" list. Read it first.
2. `docs/REPRODUCIBILITY.md`: the full rebuild and verification order. Every validator must pass before
   reporting done.
3. `docs/plans/female-open-human-atlas-plan.md` §29 (status, order of work) and
   `docs/plans/vhf-cryosection-machine-driven-plan.md` (plan B: fidelity definition §2, closing questions
   without an anatomist §2.5, acceptance and substitution criteria for bone consensus §2.6, agentic
   review experiment §3.6).
4. Open anatomical questions: `docs/plans/vhf-s1-lumbosacral-dossier.md`, `registry/review-status.json`.

## Rules that do not bend

- Nothing in this atlas is anatomically validated. Never write "validated", "confirmed" or "correct" for
  a mesh, a name, a registration or a fit. Model agreement is agreement between similar models on one
  CT: never a probability of being right, never anatomical confidence, never independent validation.
- Names of consensus instances stay `name_status: pending` until a decision is recorded in
  `registry/review-status.json`. Never impose 24/25 vertebrae or five/six lumbar as truth; the donor has
  six lumbar-type bodies and the lumbosacral transition is open.
- No anatomist (user decision, 13 September 2026, agreed by Claude and the Codex auditor): no human
  anatomical review is expected during this project. The blinded audit and the sealed test set drawn by a
  human (plan B §2.3, §2.4) move to an optional final stage 8 that happens only if the project gains
  attention. Nothing waits for it. `inspected` and `batch-audited` are not granted now and stay reserved
  for stage 8. Documentation and automatic checks are exhausted before any question is parked as open.
- Terminal status without an anatomist: `machine-accepted` (plan B §2.7) = a frozen result that passes a
  versioned automatic protocol for a stated region, set of classes and use, with no human anatomical
  review. It is bound by hash to the images, masks and meshes it graded; its criteria are fixed before
  evaluation and include negative controls; it is scored on frozen Denver bands where Denver exists and,
  elsewhere, reports consistency, never anatomical accuracy. Technical acceptance (`machine-accepted` /
  `machine-failed` / `machine-not-assessable`), name (`pending` / `documented`) and placement carry
  separate states. Never call it validation.
- New machine outputs enter as `machine-unverified` candidates and alternatives. `machine-accepted`
  enables a recorded per-structure decision to enter the composite with its status and limits visible;
  it never substitutes automatically (`registry/composition-recipe.json`). `machine-unverified`,
  `machine-failed` and `machine-not-assessable` stay in a separate layer, off by default. Denver
  (measured from the cryosections) stays wherever it is used unless a documented comparison and a
  recorded decision say otherwise.
- Work order (13 September 2026): block C, the cryosection segmentation (plan B stages 0 to 7), is the
  current work. The CT atlas is touched only when it is a prerequisite of the stage in progress. Audit
  findings that do not compromise provenance or data go to the backlog and do not stop block C.
- Sex rule: no male anatomy anywhere in the label path (no BodyParts3D as prior, no Denver male, no
  Voxel-Man). Mixed-sex CT segmentation tools are fine as naming tools on the female donor's own CT.
- Licence rule: only redistributable, commercial-use-compatible sources ship (`datasets.csv`,
  `scripts/check-licenses.py`). TotalSegmentator `total` only; licensed subtasks, VISTA3D, nnInteractive,
  MedSAM2 weights, AustinWoman, Visible Korean, Teeth3DS are excluded. NLM attribution is mandatory.
- Measurement honesty: separate `unsupported` / `unprocessed` / `absorbed` from `negative`; separate
  segmentation error from registration and posture; bounding-box gaps are not continuity; a passing
  validator is not anatomy.
- No contact with HRA, Denver, NIH, SAE, forums or authors without a separate authorisation from the user.
  No training runs, large downloads or specialised imports without a separate decision.

## Pipeline order (never skip a step)

`ingest-*.py` -> `node scripts/optimize-anatomy.mjs <atlas> <lod-prefix>` -> `build-registry.py` ->
`compose-female.py` -> `qa-geometry.py` -> `qa-anatomy.py` -> `build-registry.py` -> validators.
QA results follow a mesh only under its `geometry_sha256` (`scripts/qa_identity.py`); a rebuild that skips
`qa-anatomy.py` ships `not-assessed` and the validators now refuse that state.

The full pipeline applies to changes that touch geometry, labels or registration. Documentation, viewer
code or a validator alone do not require regenerating data; they still require the checks below that
apply (tsc and the panel test for the viewer, the validators for a validator change).

Definition of done for any change that touches data or scripts:

```bash
.venv/bin/python scripts/validate-composition.py
.venv/bin/python scripts/validate-provenance.py
.venv/bin/python scripts/validate-reviews.py
.venv/bin/python scripts/validate-consensus-metadata.py
.venv/bin/python scripts/test-consensus-metadata.py
.venv/bin/python scripts/test-qa-carryover.py
.venv/bin/python scripts/test-cryosection-transform.py
.venv/bin/python scripts/validate-cryo-pilot.py
.venv/bin/python scripts/test-cryo-pilot-validator.py
.venv/bin/python scripts/test-cryo-metrics.py
.venv/bin/python scripts/test-denver-rasteriser.py
.venv/bin/python scripts/test-cryo-pilot-evaluator.py
node --experimental-strip-types scripts/test-agreement-panel.mjs
npx tsc --noEmit
```

Then update `docs/PROGRESS.md` (and §29 of the plan when the order of work changes).

## Audit cadence (agreed 12 September 2026 between Claude and the Codex auditor)

One code audit per milestone (ingestion, composition), not per commit. Findings go to a prioritised
backlog unless they compromise provenance, published results or risk data loss; those are fixed first.
Auditor reports are relayed by the user; an audit is not a gate for every change. Every audit states
the revision examined, the checks actually run and its limits (no anatomical validation, no full visual
inspection). Auditing authorises nothing else: the auditor neither fixes, commits nor pushes.

## Git and files

- The user asks for commits and pushes explicitly. Do not commit or push on your own initiative.
- Branch `female-open-atlas`, remote `origin` (github.com/rubdttcom/human-atlas). Never commit
  `docs/substack-*.md` (excluded in `.git/info/exclude`). Keep `/data/derived/`, `/.venv-seg/` and other
  large directories ignored: Tailwind scans every non-ignored file.
- Large inputs live outside git under `data/raw/`, `data/derived/`, `sources/`. Skellytour and MOOSE
  outputs come from the GPU box `rub-pc` (see the user's notes); copy, never recompute casually.

## Environment quirks

- Python scripts run with `.venv/bin/python` (system `python3` lacks numpy; `build-registry.py` and the
  validators of registries run with `python3` as documented). TotalSegmentator lives in `.venv-seg`.
- The `rtk` shell hook rewrites some commands: `tail -N`, `grep -v` and `cat` of several files get
  mangled; use `sed -n '$p'`, python one-liners or the Read tool. `npm run check` gets mangled: use
  `npx tsc --noEmit`.
- Long jobs: launch with `setsid nohup CMD > log 2>&1 & echo $! > pidfile`, wait on a sentinel line in
  the log (every long script ends with one JSON line), never `pgrep -f` / `pkill -f` with text that
  appears in your own command line (it matches the wrapper shell and kills the tool). Launch in a
  separate step after a patch is confirmed. Give ETAs with the absolute clock time.
- Herdr: the agents exchange messages with `herdr agent prompt <pane> "..." --wait` and
  `herdr agent read <pane>` when the user asks them to talk. Pane ids change between sessions: run
  `herdr agent list` and pick the pane by agent kind and cwd before sending anything (on 12 September
  2026 Claude was `w2J:p1` and the Codex auditor `w2J:p5`).
