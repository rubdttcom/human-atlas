#!/usr/bin/env python3
"""Seed read-back of scripts/record-nnunet-run.py.

Since 2026-09-15 the launchers on the training box delegate to cryo-entry.py, which writes `SEED = 12345` and then
`random.seed(SEED)`: a literal-only scan reported seed null for the 503 run on 2026-09-21. The scan now resolves a
name to the single integer assignment of that name in the same file, and refuses a name with none or several.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('record_nnunet_run', ROOT / 'scripts/record-nnunet-run.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CASES = [
    ('literal seeds, all equal', 'random.seed(7)\nnp.random.seed(7)\ntorch.manual_seed(7)\n', ([7], [])),
    ('one name resolved', 'SEED = 12345\nrandom.seed(SEED)\ntorch.manual_seed(SEED)\ntorch.cuda.manual_seed_all(SEED)\n', ([12345], [])),
    ('name with a trailing comment', 'SEED = 42  # fixed\nrandom.seed(SEED)\n', ([42], [])),
    ('name never assigned', 'random.seed(X)\n', ([], ['X'])),
    ('name assigned twice', 'A = 1\nA = 2\nrandom.seed(A)\n', ([], ['A'])),
    ('name and literal that differ', 'S = 3\nrandom.seed(S)\ntorch.manual_seed(5)\n', ([3, 5], [])),
    ('epoch time line is not a seed', 'Epoch time: 43.31 s\n', ([], [])),
    ('shell launcher without any seeding call', '#!/usr/bin/env bash\nexport PYTHONHASHSEED=12345\n', ([], [])),
]

failed = 0
for name, text, want in CASES:
    got = mod.seeds_in(text)
    ok = got == want
    failed += not ok
    print(('ok   ' if ok else 'FAIL ') + name + ('' if ok else f': got {got}, want {want}'))
print(f'{len(CASES) - failed}/{len(CASES)} cases pass')
sys.exit(1 if failed else 0)
