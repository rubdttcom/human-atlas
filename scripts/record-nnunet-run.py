"""Record what a training run actually was, read from the training box and from nothing else.

Runs ON the GPU box with the nnU-Net environment. It exists because the training manifest used to take the seed, the
nnU-Net version and the run history as operator-typed arguments, which look authoritative in a report while being
assertions (audit of the uncommitted pilot code, findings 1 and 2). Everything below is read from disk or from the
installed library:

  nnunetv2_version      nnunetv2.__version__ of the environment that ran the training
  torch, gpu            torch.__version__ and the device name
  runs_observed         one entry per training_log_*.txt in fold_0, with its start time and last logged epoch; nnU-Net
                        writes a new log file on every training start, so this is the run history, not a declaration
  weights_sha256        checkpoint_final.pth, and checkpoint_latest.pth when the run is unfinished
  launcher              the sha256 and the seed line of the shell script that started the run
  plans, fingerprint    the preprocessed files nnU-Net actually used

Seeding. nnUNetv2_train has no seed flag. The launcher seeds random, numpy and torch in the main process before calling
run_training, and that value is read back from the launcher here. nnU-Net passes seeds=None to its batch-generator
worker processes, so augmentation is NOT seeded and the run is not bit-reproducible. That limit is written into the
record; the seed describes the main process and nothing more.

  env-nnunet/bin/python record-nnunet-run.py --results <nnUNet_results>/Dataset501_.../nnUNetTrainer__nnUNetPlans__2d \
      --preprocessed <nnUNet_preprocessed>/Dataset501_... --launcher run-cryo-train.sh --out run-provenance-501.json

Nothing here is anatomy.
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

# nnU-Net writes "2026-09-13 17:50:20.236377: Epoch 0 ". The earlier pattern used [^:]* for the timestamp,
# which cannot cross the colons of the clock, so it never matched and last_epoch_logged was always null
# (Codex audit of 909e500). "Epoch time: 43.31 s" must still not match: digits are required before the end.
EPOCH_LINE = re.compile(r'^(?:.*\s)?Epoch (\d+)\s*$', re.M)
# every seeding call a launcher may make, not only random.seed: a launcher that seeded torch differently
# used to be reported as a single clean seed (Codex audit of 909e500)
SEED_LINE = re.compile(r'(?:random|np\.random|numpy\.random|torch|torch\.cuda)\.'
                       r'(?:seed|manual_seed|manual_seed_all)\(\s*(\d+)\s*\)')


def sha256_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', required=True)
    ap.add_argument('--preprocessed', required=True)
    ap.add_argument('--launcher', required=True)
    ap.add_argument('--fold', type=int, default=0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    res, prep, launcher = Path(a.results), Path(a.preprocessed), Path(a.launcher)
    fold = res / f'fold_{a.fold}'
    rec = {'id': 'nnunet-run-provenance', 'date': time.strftime('%Y-%m-%d %H:%M:%S'),
           'results': str(res), 'preprocessed': str(prep), 'fold': a.fold}

    import importlib.metadata as md
    import nnunetv2
    import torch
    # nnunetv2 exposes no __version__ attribute; the installed distribution metadata is the only readable source
    try:
        rec['nnunetv2_version'] = md.version('nnunetv2')
    except md.PackageNotFoundError:
        rec['nnunetv2_version'] = None
    rec['nnunetv2_path'] = str(Path(nnunetv2.__file__).parent)
    rec['torch_version'] = torch.__version__
    rec['gpu'] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None

    # one log file per training start: this is the observed run history
    runs = []
    for log in sorted(fold.glob('training_log_*.txt')):
        text = log.read_text(errors='replace')
        epochs = [int(m) for m in EPOCH_LINE.findall(text)]
        runs.append({'log': log.name, 'started': log.name[len('training_log_'):-len('.txt')],
                     'last_epoch_logged': max(epochs) if epochs else None,
                     'bytes': log.stat().st_size, 'sha256': sha256_file(log)})
    rec['runs_observed'] = runs
    rec['runs_observed_count'] = len(runs)

    for name in ('checkpoint_final.pth', 'checkpoint_latest.pth', 'checkpoint_best.pth'):
        p = fold / name
        if p.exists():
            rec.setdefault('checkpoints', {})[name] = {'sha256': sha256_file(p), 'bytes': p.stat().st_size}
    if (fold / 'checkpoint_final.pth').exists():
        rec['weights_sha256'] = rec['checkpoints']['checkpoint_final.pth']['sha256']
        rec['complete'] = True
    else:
        rec['complete'] = False

    for key, p in (('plans', prep / 'nnUNetPlans.json'), ('fingerprint', prep / 'dataset_fingerprint.json'),
                   ('splits', prep / 'splits_final.json'), ('dataset_json', prep / 'dataset.json')):
        if p.exists():
            rec[key + '_sha256'] = sha256_file(p)
    # the split ACTUALLY installed, so the manifest writer can bind the run to the frozen one instead of
    # trusting the dataset name the operator typed (Codex audit of 909e500, P1-2)
    sp = prep / 'splits_final.json'
    if sp.exists():
        splits = json.loads(sp.read_text())
        rec['splits_folds'] = len(splits)
        if 0 <= a.fold < len(splits):
            rec['split_counts'] = [len(splits[a.fold]['train']), len(splits[a.fold]['val'])]
    if (prep / 'dataset.json').exists():
        dj = json.loads((prep / 'dataset.json').read_text())
        rec['dataset_channel_names'] = dj.get('channel_names')
        rec['dataset_labels'] = dj.get('labels')
    if (prep / 'nnUNetPlans.json').exists():
        plans = json.loads((prep / 'nnUNetPlans.json').read_text())
        rec['plans_identifier'] = plans.get('plans_name', 'nnUNetPlans')
        cfg = plans.get('configurations', {}).get('2d', {})
        rec['configuration_2d'] = {k: cfg.get(k) for k in
                                   ('patch_size', 'batch_size', 'spacing', 'median_image_size_in_voxels',
                                    'normalization_schemes')}

    if launcher.exists():
        text = launcher.read_text()
        seeds = sorted({int(m) for m in SEED_LINE.findall(text)})
        rec['launcher'] = {'path': str(launcher), 'sha256': sha256_file(launcher),
                           'seeds_found_in_launcher': seeds}
        # one value only is a seed; several different ones are not one seed and are not reported as one
        rec['seed'] = seeds[0] if len(seeds) == 1 else None
        if len(seeds) != 1:
            rec.setdefault('seed_limits', []).append(
                f'the launcher sets {len(seeds)} different seed values {seeds}; no single seed describes the run')
    rec['seed_limits'] = rec.get('seed_limits', []) + [
        'nnUNetv2_train has no seed flag; the value is the one the launcher applies to random, numpy and torch in the main process',
        'nnU-Net passes seeds=None to its batch-generator workers, so augmentation is unseeded and the run is not bit-reproducible',
        'cuDNN benchmarking is on by default, which makes some kernels non-deterministic as well',
    ]
    Path(a.out).write_text(json.dumps(rec, indent=1) + '\n')
    print(json.dumps({'ok': True, 'out': a.out, 'runs_observed': len(runs), 'complete': rec['complete'],
                      'nnunetv2_version': rec['nnunetv2_version'], 'seed': rec.get('seed')}))


if __name__ == '__main__':
    main()
