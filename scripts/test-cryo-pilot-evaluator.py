"""Gate tests of scripts/cryo-pilot-evaluate-v2.py (from the Codex audit of 8a5da4b, two P1; moved to version 2 on 2026-09-20): every refused input below must produce a
report with every class machine-not-assessable and exit 1 BEFORE any score, and the reasons must be the expected ones.
Runs the evaluator as a subprocess on the real block with synthetic predictions written to a temporary directory; no gate
case takes more than a few seconds because scoring never starts.

Cases (version 2 adds: a run started before the protocol date, an undated run): prediction with a translated affine; labels 256..259 in int16 (would wrap to 0..3 if cast); float dtype; a label
value outside the active classes; a block directory whose manifest differs from the frozen one (identity mismatch); no
training manifest; a training manifest with a band slice, with an auxiliary slice, with a missing field, with too many runs.
A well-formed training manifest with a valid prediction is NOT run here (12 minutes); the oracle run is the positive case.

  .venv/bin/python scripts/test-cryo-pilot-evaluator.py
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BLOCK = ROOT / 'data/derived/nlm-vhf/cryosections/block2'
EVAL = ROOT / 'scripts/cryo-pilot-evaluate-v2.py'
PY = sys.executable
results = {}


def case(name, ok, detail=''):
    results[name] = bool(ok)
    if not ok:
        print('FAILED', name, detail)


def run(args, out):
    r = subprocess.run([PY, str(EVAL), '--block', str(BLOCK), '--variant', 'test', '--out', str(out)] + args, capture_output=True, text=True, timeout=900)
    rep = json.loads(Path(out).read_text()) if Path(out).exists() else None
    return r.returncode, rep, r.stdout + r.stderr


if not BLOCK.exists():
    print(json.dumps({'skipped': 'block not on disk', 'cases': 0, 'all_as_expected': True})); sys.exit(0)

ref_img = nib.load(str(BLOCK / 'tissue-classes.nii.gz'))
ref = np.asarray(ref_img.dataobj)
bands = json.loads((ROOT / 'registry/cryo-eval-bands-v1.json').read_text())
te = bands['training_eligibility']
primary = [k for lo, hi in te['primary_k_ranges'] for k in range(lo, hi + 1)]
prot = json.loads((ROOT / 'registry/machine-acceptance-protocol-v2.json').read_text())
prot_sha = hashlib.sha256((ROOT / 'registry/machine-acceptance-protocol-v2.json').read_bytes()).hexdigest()
good_run = {'run': 1, 'status': 'completed', 'started': '2026_9_21_00_00_00', 'log': 'training_log_2026_9_21_00_00_00.txt'}
good_train = {'training_slices_k': primary, 'weights_sha256': '0' * 64, 'nnunetv2_version': '2.8.1', 'dataset_fingerprint': 'x', 'plans_identifier': 'nnUNetPlans', 'seed': 12345, 'fold': 0,
              'runs': [good_run], 'runs_observed': [good_run], 'protocol_sha256': prot_sha}
valid_pred = np.where(ref == 255, 0, ref).astype(np.uint8)          # a legal prediction volume (ignore is not an output class)

with tempfile.TemporaryDirectory() as td:
    td = Path(td)

    def write_pred(arr, affine, name):
        p = td / name; nib.save(nib.Nifti1Image(arr, affine), str(p)); return p

    def write_train(doc, name):
        p = td / name; p.write_text(json.dumps(doc)); return p

    train_ok = write_train(good_train, 'train-ok.json')

    aff = ref_img.affine.copy(); aff[0, 3] += 1000.0
    code, rep, log = run(['--prediction', str(write_pred(valid_pred, aff, 'translated.nii.gz')), '--training-manifest', str(train_ok)], td / 'r1.json')
    case('translated_affine_refused', code == 1 and rep and rep['gate_failed'] == 'prediction volume rejected' and any('affine' in p for p in rep['prediction_problems']), log[-300:])

    wrapped = (valid_pred.astype(np.int16) + 256)
    code, rep, log = run(['--prediction', str(write_pred(wrapped, ref_img.affine, 'wrapped.nii.gz')), '--training-manifest', str(train_ok)], td / 'r2.json')
    case('int16_256_refused_not_wrapped', code == 1 and rep and rep['gate_failed'] == 'prediction volume rejected', log[-300:])

    code, rep, log = run(['--prediction', str(write_pred(valid_pred.astype(np.float32), ref_img.affine, 'float.nii.gz')), '--training-manifest', str(train_ok)], td / 'r3.json')
    case('float_dtype_refused', code == 1 and rep and rep['gate_failed'] == 'prediction volume rejected' and any('integral' in p for p in rep['prediction_problems']), log[-300:])

    bad = valid_pred.copy(); bad[0, 0, 0] = 7
    code, rep, log = run(['--prediction', str(write_pred(bad, ref_img.affine, 'badval.nii.gz')), '--training-manifest', str(train_ok)], td / 'r4.json')
    case('label_outside_active_classes_refused', code == 1 and rep and any('outside the active output classes' in p for p in rep['prediction_problems']), log[-300:])

    code, rep, log = run(['--prediction', str(write_pred(valid_pred, ref_img.affine, 'ok.nii.gz'))], td / 'r5.json')
    case('no_training_manifest_refused', code == 1 and rep and rep['gate_failed'].startswith('training provenance'), log[-300:])

    leak = dict(good_train); leak['training_slices_k'] = primary + [bands['bands'][0]['k_first']]
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(leak, 'leak.json'))], td / 'r6.json')
    case('band_slice_in_training_refused', code == 1 and rep and any('band or buffer' in p for p in rep['training_problems']), log[-300:])

    aux = dict(good_train); aux['training_slices_k'] = primary + [te['auxiliary_k_ranges'][0][0]]
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(aux, 'aux.json'))], td / 'r7.json')
    case('auxiliary_slice_in_training_refused', code == 1 and rep and any('auxiliary' in p for p in rep['training_problems']), log[-300:])

    missing = dict(good_train); missing['weights_sha256'] = None
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(missing, 'missing.json'))], td / 'r8.json')
    case('missing_weights_hash_refused', code == 1 and rep and any('weights_sha256' in p for p in rep['training_problems']), log[-300:])

    many = dict(good_train); many['runs'] = [dict(good_run, run=i) for i in range(3)]; many['runs_observed'] = list(many['runs'])
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(many, 'many.json'))], td / 'r9.json')
    case('iteration_limit_enforced', code == 1 and rep and any('iteration limit' in p for p in rep['training_problems']), log[-300:])

    # version 2 applicability: a run that started before the protocol date is not assessable under version 2
    early = dict(good_train); early['runs'] = [{'run': 1, 'status': 'completed', 'started': '2026_9_14_17_09_18'}]
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(early, 'early.json'))], td / 'r11.json')
    case('pre_v2_training_run_refused', code == 1 and rep and any('before the protocol freeze instant' in p for p in rep['training_problems']), log[-300:])
    undated = dict(good_train); undated['runs'] = [{'run': 1, 'status': 'completed'}]
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(undated, 'undated.json'))], td / 'r12.json')
    case('undated_training_run_refused', code == 1 and rep and any('without a parseable start instant' in p for p in rep['training_problems']), log[-300:])
    # external audit of b02dd3b, finding 1: a runs OBJECT skipped the date and limit checks; the protocol day alone passed
    asdict = dict(good_train); asdict['runs'] = {'run': 1, 'status': 'completed', 'started': '2026_9_14_17_09_18'}
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(asdict, 'asdict.json'))], td / 'r13.json')
    case('runs_object_refused', code == 1 and rep and any('non-empty list' in p for p in rep['training_problems']), log[-300:])
    empty = dict(good_train); empty['runs'] = []
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(empty, 'empty.json'))], td / 'r14.json')
    case('empty_runs_refused', code == 1 and rep and any('non-empty list' in p or 'missing or empty: runs' in p for p in rep['training_problems']), log[-300:])
    freeze = prot['applicability']['training_started_after']            # 'YYYY-MM-DD HH:MM:SS'
    day = freeze[:10].replace('-', '_')
    sameday = dict(good_train); sameday['runs'] = [dict(good_run, started=day + '_00_00_01')]; sameday['runs_observed'] = list(sameday['runs'])
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(sameday, 'sameday.json'))], td / 'r15.json')
    case('protocol_day_before_freeze_instant_refused', code == 1 and rep and any('before the protocol freeze instant' in p for p in rep['training_problems']), log[-300:])
    dateonly = dict(good_train); dateonly['runs'] = [dict(good_run, started='2026-09-21')]; dateonly['runs_observed'] = list(dateonly['runs'])
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(dateonly, 'dateonly.json'))], td / 'r16.json')
    case('date_without_time_refused', code == 1 and rep and any('without a parseable start instant' in p for p in rep['training_problems']), log[-300:])
    obs_early = dict(good_train); obs_early['runs_observed'] = [dict(good_run, started='2026_9_14_17_09_18')]
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(obs_early, 'obs_early.json'))], td / 'r17.json')
    case('observed_log_before_freeze_refused', code == 1 and rep and any('observed training log started' in p for p in rep['training_problems']), log[-300:])
    otherprot = dict(good_train); otherprot['protocol_sha256'] = '1' * 64
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(otherprot, 'otherprot.json'))], td / 'r18.json')
    case('other_protocol_revision_refused', code == 1 and rep and any('bound to protocol revision' in p for p in rep['training_problems']), log[-300:])
    mismatch = dict(good_train); mismatch['runs_observed'] = [good_run, dict(good_run, run=2)]
    code, rep, log = run(['--prediction', str(td / 'ok.nii.gz'), '--training-manifest', str(write_train(mismatch, 'mismatch.json'))], td / 'r19.json')
    case('declared_vs_observed_count_refused', code == 1 and rep and any('training logs observed' in p for p in rep['training_problems']), log[-300:])

    # identity mismatch: a copy of the block with an edited manifest
    fake = td / 'block'; fake.mkdir()
    for f in ('manifest.json', 'tissue-classes.nii.gz'):
        shutil.copy(BLOCK / f, fake / f)
    m = json.loads((fake / 'manifest.json').read_text()); m['note'] = 'edited'; (fake / 'manifest.json').write_text(json.dumps(m))
    r = subprocess.run([PY, str(EVAL), '--block', str(fake), '--oracle', '--out', str(td / 'r10.json')], capture_output=True, text=True, timeout=900)
    rep = json.loads((td / 'r10.json').read_text()) if (td / 'r10.json').exists() else None
    case('foreign_block_identity_mismatch', r.returncode == 1 and rep and rep['gate_failed'].startswith('inputs differ') and 'rgb_block_manifest_sha256' in rep['identity_mismatch'], (r.stdout + r.stderr)[-300:])
    for rp in td.glob('r*.json'):
        rep = json.loads(rp.read_text())
        if rep.get('gate_failed') and any(c['status'] != 'machine-not-assessable' for c in rep['classes'].values()):
            case('refused_report_all_not_assessable', False, rp.name)
    results.setdefault('refused_report_all_not_assessable', True)

ok = all(results.values())
print(json.dumps({'cases': len(results), 'all_as_expected': ok, 'failed': [k for k, v in results.items() if not v]}))
sys.exit(0 if ok else 1)
