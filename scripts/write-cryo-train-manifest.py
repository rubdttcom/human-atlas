"""Write the training manifest the evaluator's training gate requires, from what the run actually produced.

No field is typed by hand. The slice list comes from the dataset report; everything about the run comes from the
provenance record that scripts/record-nnunet-run.py wrote ON the training box by reading the results folder, the
preprocessed folder, the launcher and the installed nnU-Net. A field that cannot be read is left missing, and the
evaluator then records "training provenance incomplete" and accepts no class. That is intended: it is never guessed.

The operator still declares the run history in --run, because only a person knows WHY a run happened. The declaration
is checked against the training_log_*.txt files nnU-Net wrote: nnU-Net starts a new log on every training start, so a
declaration that hides an attempt is refused here (audit of the uncommitted pilot code, finding 2). The protocol's
iteration limit is worth nothing if the run count is free text.

Version 2 (2026-09-20, after the external audit of b02dd3b): each declared run receives the start stamp, name and hash of
its training log (declared runs are typed, and the applicability gate needs the observed instant), and the manifest
names the protocol revision it was written under (protocol_sha256), which the evaluator compares with the file it reads.

Two refusals were added after the Codex audit of 1af1c60.

P1-2: --variant chose the dataset report and --provenance was any file, with nothing tying them together, so an rgb-only
report combined with a provenance naming Dataset502 and six channels was written and then accepted. bind_gate() now
compares the dataset the run actually used against the report: the results and preprocessed paths must name that
dataset, the channel count of the plan's normalisation schemes must equal the report's, and the installed split must be
the frozen one the report describes. Names chosen by the operator are not enough.

P1-3: a manifest with problems was still WRITTEN before the script exited 1, and the evaluator's training gate reads
neither consistency_problems nor runs_observed, so the rejected file passed it. The evaluator is frozen by hash and is
not touched. Instead a rejected manifest is never written at the requested path: it goes to <out>.rejected.json, so no
file exists that the evaluator could accept. The refusal now sits at the real acceptance boundary.

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
            'plans_identifier', 'seed', 'fold', 'runs', 'runs_observed', 'protocol_sha256')
PROTOCOL = ROOT / 'registry/machine-acceptance-protocol-v2.json'


def sha256_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def bind_gate(ds, prov):
    """Tie the provenance to the dataset report. Names alone prove nothing (Codex audit of 1af1c60, P1-2)."""
    problems = []
    name = ds['dataset_name']
    for key in ('results', 'preprocessed'):
        got = str(prov.get(key, ''))
        if name not in got:
            problems.append(f'provenance {key} path {got!r} does not name the report dataset {name}')
    cfg = prov.get('configuration_2d') or {}
    schemes = cfg.get('normalization_schemes')
    if schemes is None:
        problems.append('provenance has no configuration_2d.normalization_schemes: the trained channels are unknown')
    elif len(schemes) != len(ds['channels']):
        problems.append(f'the run trained {len(schemes)} channels, the report describes {len(ds["channels"])}')
    folds = ds['split'].get('folds') or []
    if prov.get('fold') != ds['split'].get('fold_trained'):
        problems.append(f'the run trained fold {prov.get("fold")}, the report freezes fold {ds["split"].get("fold_trained")}')
    obs = prov.get('split_counts')
    if obs and folds:
        want = [folds[prov['fold']]['train'], folds[prov['fold']]['val']]
        if list(obs) != want:
            problems.append(f'the installed split of the trained fold is {list(obs)}, the report freezes {want}')
    elif not obs:
        problems.append('provenance has no split_counts: the split actually installed is unknown')
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', required=True)
    ap.add_argument('--provenance', required=True, help='the record written by scripts/record-nnunet-run.py')
    ap.add_argument('--run', action='append', default=[], help='one JSON object per training run, in order')
    ap.add_argument('--out', default=None)
    ap.add_argument('--prior-version', type=int, choices=[1, 2], default=1,
                    help='rgb-plus-ct-prior only: 2 reads the dataset report of the version 2 prior (dataset 503) and names the manifest -v2')
    a = ap.parse_args()

    tag = '-v2' if a.prior_version == 2 else ''
    ds_report = ROOT / f'generated/cryo-nnunet-dataset-block2-{a.variant}{tag}.json'
    ds = json.loads(ds_report.read_text())
    if a.prior_version == 2 and ds.get('prior_version') != 2:
        raise SystemExit(json.dumps({'ok': False, 'error': f'{ds_report.name} does not describe a version 2 prior build'}))
    prov_path = Path(a.provenance)
    prov = json.loads(prov_path.read_text())

    declared = [json.loads(r) for r in a.run]
    observed = prov.get('runs_observed', [])
    problems = bind_gate(ds, prov)
    if len(declared) != len(observed):
        problems.append(f'{len(declared)} runs declared against {len(observed)} training logs on the training box')
    else:
        # the start instant of a run is read from the training log nnU-Net wrote, never typed: the version 2 evaluator's
        # applicability gate compares it with the protocol's freeze instant (external audit of b02dd3b, finding 1)
        for d, o in zip(declared, observed):
            d['started'] = o.get('started'); d['log'] = o.get('log'); d['log_sha256'] = o.get('sha256')
    if not prov.get('complete'):
        problems.append('the provenance record has no checkpoint_final.pth: the training did not finish')

    man = {
        'id': f'cryo-nnunet-train-block2-{a.variant}{tag}', 'date': time.strftime('%Y-%m-%d'), 'variant': a.variant,
        'prior_version': ds.get('prior_version'),
        'training_slices_k': ds['training_slices_k'],
        'fold': prov.get('fold'), 'seed': prov.get('seed'),
        'nnunetv2_version': prov.get('nnunetv2_version'),
        'weights_sha256': prov.get('weights_sha256'),
        'dataset_fingerprint': prov.get('fingerprint_sha256'),
        'plans_identifier': prov.get('plans_identifier'),
        'runs': declared,
        'runs_observed': observed,
        'protocol_sha256': sha256_file(PROTOCOL), 'protocol': str(PROTOCOL.relative_to(ROOT)), 'protocol_version': json.loads(PROTOCOL.read_text())['version'],
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

    out = Path(a.out) if a.out else ROOT / f'generated/cryo-nnunet-train-block2-{a.variant}{tag}.json'
    missing = [f for f in REQUIRED if not man.get(f) and man.get(f) != 0]
    # A rejected manifest is never written where the evaluator would read it. The evaluator's training gate
    # reads neither consistency_problems nor runs_observed, and it is frozen by hash, so the refusal has to
    # be here: no acceptable file is produced at all (Codex audit of 1af1c60, P1-3).
    if missing or problems:
        out = out.with_suffix('.rejected.json')
        man['REJECTED'] = 'this manifest was refused; it is not a training record and the evaluator must not read it'
    out.write_text(json.dumps(man, indent=1) + '\n')
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out   # --out may point outside the repo
    print(json.dumps({'ok': not missing and not problems, 'out': str(shown),
                      'missing': missing, 'problems': problems,
                      'training_slices': len(man['training_slices_k']),
                      'runs_declared': len(declared), 'runs_observed': len(observed)}))
    if missing or problems:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
