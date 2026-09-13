"""Write the training manifest the evaluator's training gate requires, from what the run actually produced.

No field is typed by hand. The slice list comes from the dataset report; everything about the run comes from the
provenance record that scripts/record-nnunet-run.py wrote ON the training box by reading the results folder, the
preprocessed folder, the launcher and the installed nnU-Net. A field that cannot be read is left missing, and the
evaluator then records "training provenance incomplete" and accepts no class. That is intended: it is never guessed.

The operator still declares the run history in --run, because only a person knows WHY a run happened. The declaration
is checked against the training_log_*.txt files nnU-Net wrote: nnU-Net starts a new log on every training start, so a
declaration that hides an attempt is refused here (audit of the uncommitted pilot code, finding 2). The protocol's
iteration limit is worth nothing if the run count is free text.

  .venv/bin/python scripts/write-cryo-train-manifest.py --variant rgb-only \
      --provenance generated/nnunet-run-provenance-501.json \
      --run '{"run": 1, "status": "completed", "date": "2026-09-14", "reason": "first run"}'

Nothing here is anatomy.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('training_slices_k', 'weights_sha256', 'nnunetv2_version', 'dataset_fingerprint',
            'plans_identifier', 'seed', 'fold', 'runs')


def sha256_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', required=True)
    ap.add_argument('--provenance', required=True, help='the record written by scripts/record-nnunet-run.py')
    ap.add_argument('--run', action='append', default=[], help='one JSON object per training run, in order')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    ds_report = ROOT / f'generated/cryo-nnunet-dataset-block2-{a.variant}.json'
    ds = json.loads(ds_report.read_text())
    prov_path = Path(a.provenance)
    prov = json.loads(prov_path.read_text())

    declared = [json.loads(r) for r in a.run]
    observed = prov.get('runs_observed', [])
    problems = []
    if len(declared) != len(observed):
        problems.append(f'{len(declared)} runs declared against {len(observed)} training logs on the training box')
    if not prov.get('complete'):
        problems.append('the provenance record has no checkpoint_final.pth: the training did not finish')

    man = {
        'id': f'cryo-nnunet-train-block2-{a.variant}', 'date': time.strftime('%Y-%m-%d'), 'variant': a.variant,
        'training_slices_k': ds['training_slices_k'],
        'fold': prov.get('fold'), 'seed': prov.get('seed'),
        'nnunetv2_version': prov.get('nnunetv2_version'),
        'weights_sha256': prov.get('weights_sha256'),
        'dataset_fingerprint': prov.get('fingerprint_sha256'),
        'plans_identifier': prov.get('plans_identifier'),
        'runs': declared,
        'runs_observed': observed,
        'provenance': {'path': str(prov_path), 'sha256': sha256_file(prov_path),
                       'torch_version': prov.get('torch_version'), 'gpu': prov.get('gpu'),
                       'launcher': prov.get('launcher'), 'checkpoints': prov.get('checkpoints'),
                       'plans_sha256': prov.get('plans_sha256'), 'splits_sha256': prov.get('splits_sha256'),
                       'configuration_2d': prov.get('configuration_2d')},
        'dataset': {'id': ds['dataset_id'], 'name': ds['dataset_name'], 'channels': ds['channels'],
                    'channel_meaning': ds['channel_meaning'], 'report': str(ds_report.relative_to(ROOT)),
                    'report_sha256': sha256_file(ds_report)},
        'split': ds['split'],
        'inputs': ds['inputs'],
        'ignore_encoding': ds.get('ignore_encoding'),
        'slice_axis_spacing': ds.get('slice_axis_spacing'),
        'limits': ds['limits'] + prov.get('seed_limits', []) + [
            'the declared run history is checked against one training log per training start; a run that left no log '
            'on this box cannot be seen here',
        ],
        'consistency_problems': problems,
    }

    out = Path(a.out) if a.out else ROOT / f'generated/cryo-nnunet-train-block2-{a.variant}.json'
    out.write_text(json.dumps(man, indent=1) + '\n')
    missing = [f for f in REQUIRED if not man.get(f) and man.get(f) != 0]
    print(json.dumps({'ok': not missing and not problems, 'out': str(out.relative_to(ROOT)),
                      'missing': missing, 'problems': problems,
                      'training_slices': len(man['training_slices_k']),
                      'runs_declared': len(declared), 'runs_observed': len(observed)}))
    if missing or problems:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
