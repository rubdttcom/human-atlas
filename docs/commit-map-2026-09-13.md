# Commit map of the 2026-09-13 history rewrite

Every commit of this fork was rewritten on 2026-09-13 to remove an email address that should never
have been used here: the commits were authored with a work address instead of the account that owns
this repository. The repository is public, so the address was visible in every commit. The same pass
removed absolute `/home/...` paths from the history, which published the machine's user name.

Nothing about the content of the atlas changed. Only the author and committer identity, and those
paths, differ. Upstream commits by Ashe Magalhaes keep their own identity and are untouched.

The rewrite changed every commit hash from the first commit of this fork onwards. This project cites
commit hashes in its documents and in its code, so this table is how an old citation is resolved.
`git-filter-repo` already rewrote the hashes quoted inside commit messages; this table covers the
hashes quoted inside files.

## Citations that are deliberately NOT updated

Three files keep their old hashes on purpose, because their own sha256 is pinned in
`registry/machine-acceptance-protocol-v1.json` and editing them would void acceptance protocol v1:

| File | Stale hash it cites | Resolves to |
|---|---|---|
| `registry/machine-acceptance-protocol-v1.json` | `87ff582`, `afec927` | see the table below |
| `scripts/cryo-pilot-evaluate.py` | `87ff582` | see the table below |
| `scripts/cryo_metrics.py` | `afec927` | see the table below |

A frozen document is not edited after the fact, not even a citation inside it. That is the whole
point of freezing it.

## Full map

| # | Before | After | Date | Subject |
|---|---|---|---|---|
| 7 | `64a8376` | `81f89b9` | 2026-09-05 | Add Denver VHF lower limb source and composition 0.2 to the female atlas |
| 8 | `f830ea5` | `cdb005d` | 2026-09-05 | Composition 0.4: same-donor NLM VHF CT source, verified canonical frame, ontolog |
| 9 | `da8599b` | `44578aa` | 2026-09-05 | README: separate viewing (committed geometry) from rebuilding the data |
| 10 | `f1c09ed` | `2c1a5b5` | 2026-09-05 | Document the data release shortcut for rebuilding |
| 11 | `29171cb` | `f63296c` | 2026-09-09 | Plan B for VHF cryosection segmentation, external review reply, MOOSE bone run o |
| 12 | `94e8f75` | `792bc67` | 2026-09-09 | CT prior consensus of three models, laterality checks, Denver CT placement and S |
| 13 | `42ae41d` | `3dfa00e` | 2026-09-09 | Vertebra consensus by geometric instance, Skellytour merge provenance, plan B se |
| 14 | `78fe6c7` | `67bafd7` | 2026-09-09 | Instance consensus extended to ribs; fragment rule; Skellytour merge re-run with |
| 15 | `841d680` | `2f55ece` | 2026-09-10 | Instance consensus: geometric fragments, true unions, manifest eligibility, mm d |
| 16 | `a1a4c2b` | `3957d3d` | 2026-09-10 | Piece merging: two passes, full instances preferred as targets, chains resolved  |
| 17 | `b0063fd` | `c8fbedb` | 2026-09-12 | Ingest CT consensus as a source: composition 0.5 |
| 18 | `083589a` | `f30c55f` | 2026-09-12 | QA: keep measured results only for identical geometry; consensus vertebrae in sp |
| 19 | `553ecfb` | `6aed396` | 2026-09-12 | QA identity by SHA-256 only; composed.json carries source and composed QA |
| 20 | `23bc914` | `64eb660` | 2026-09-12 | PROGRESS: state at 6aed396 (QA recomputed for 0.5, identity rule, audit outcomes |
| 21 | `8b9112d` | `7a7c825` | 2026-09-12 | Model agreement in the viewer, plan sync, gated per-name bone candidates |
| 22 | `f28467f` | `a20cd0c` | 2026-09-12 | Ingest the nine per-name bone candidates as machine-unverified alternatives |
| 23 | `b625333` | `aa59581` | 2026-09-12 | Shared working agreement for agents (CLAUDE.md, AGENTS.md symlink) |
| 24 | `f9eab68` | `1564a31` | 2026-09-12 | Validator compares bone-candidate gates and comparisons; state the pending shape |
| 25 | `aa71a89` | `b365d46` | 2026-09-13 | Shape check of plan B 2.6 for the nine bone candidates, same procedure as the De |
| 26 | `46c4975` | `ef75020` | 2026-09-13 | No anatomist during the project: machine-accepted terminal status; block C start |
| 27 | `38308be` | `3c907b7` | 2026-09-13 | Stage 0: trunk posture offset measured and published per mesh; origin completene |
| 28 | `61ccf5c` | `7741e8c` | 2026-09-13 | Posture offset: keep split labels in the provenance link, attribute no cause, ca |
| 29 | `02d3f59` | `acbe4dd` | 2026-09-13 | Stage 0: alignment of the colour photographs against Denver's aligned slices; nl |
| 30 | `5638434` | `5deac74` | 2026-09-13 | Cryosection transform: keep per-slice identity status, refuse partial reports, e |
| 31 | `15a92a9` | `761a4c8` | 2026-09-13 | Stage 0 complete: photograph-to-CT check, CT provenance correction, observabilit |
| 32 | `afec927` | `4da4b5b` | 2026-09-13 | RGB pilot steps 1 to 4: aligned RGB volume of Denver block 2, tissue map v1, fro |
| 33 | `87ff582` | `8a5da4b` | 2026-09-13 | Codex audit of 4da4b5b applied: one frozen metric implementation, Denver floor r |
| 34 | `e39ceb8` | `38576ee` | 2026-09-13 | Codex audit of 8a5da4b applied: evaluator gates on identity, grid and training p |
| 35 | `c060d45` | `97cf1b5` | 2026-09-13 | RGB pilot step 5: nnU-Net datasets, CT prior channels and run provenance; traini |
| 36 | `ecb7629` | `1c1a331` | 2026-09-13 | Chain the second pilot variant after the first: the two cannot share the RTX 308 |
| 37 | `909e500` | `1af1c60` | 2026-09-13 | Rehearse the post-training chain on a synthetic prediction; read the SAM 3 licen |
| 38 | `a4754fa` | `7455c91` | 2026-09-13 | Codex audit of 1af1c60 applied: slice gate before conversion, provenance bound t |
| 39 | `e57d9d5` | `243bf61` | 2026-09-13 | Stop publishing absolute home paths in a public repository |

Full 40-character hashes are in `.git/filter-repo/commit-map` of the rewriting clone, and the
pre-rewrite history is kept in a local bundle outside the repository.
