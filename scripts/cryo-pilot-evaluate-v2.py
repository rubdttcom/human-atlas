"""Evaluator of the cryosection pilot under acceptance protocol VERSION 2 (registry/machine-acceptance-protocol-v2.json).

  .venv/bin/python scripts/cryo-pilot-evaluate-v2.py --block data/derived/nlm-vhf/cryosections/block2 \
      --prediction PRED.nii.gz --training-manifest TRAIN.json --variant rgb-only --out generated/cryo-pilot-acceptance-v2-block2-rgb-only.json
  .venv/bin/python scripts/cryo-pilot-evaluate-v2.py --block ... --oracle      # prediction := reference; freezes the evaluator sanity figures

Version 2 was written on 2026-09-20 AFTER the two version 1 variants had been scored (post hoc analysis in
docs/findings-2026-09-20-observable-surface-posthoc.md). scripts/cryo-pilot-evaluate.py and scripts/cryo_metrics.py stay the
frozen version 1 and are not touched. Differences from version 1, all in the protocol file: the surface metric is
scripts/cryo_metrics_v2.py (observable boundaries, reference-side class attribution, full-boundary targets, faces removed);
predicted volume on ignore is reported per class and band, never scored; cartilage carries a required-neighbour criterion
(median distance from predicted cartilage to predicted bone); and a fifth gate refuses any training run that started before
the protocol date, so that no variant scored under version 1 can be re-scored here.

Gates, all before any score is computed (Codex audit of 87ff582, two P1): nothing is graded unless
  1. the registry validator (scripts/validate-cryo-pilot.py) passes on the repository files;
  2. the ACTUAL inputs match protocol.identity_by_hash.fixed_now: manifest, tissue-classes volume and report, bands, tissue
     map, both floors, this evaluator and scripts/cryo_metrics.py, byte for byte (an --block directory from elsewhere fails);
  3. the prediction has the reference's shape AND affine (1e-6 mm), an integer dtype, finite values, and only the protocol's
     active output classes (0..3); nothing is cast or wrapped;
  4. for a non-oracle run, --training-manifest is a JSON with training_slices_k (every k in the primary eligibility of the
     bands file, none in a band, buffer or the auxiliary stratum), weights_sha256, nnunetv2_version, dataset_fingerprint,
     plans_identifier, seed, fold, runs and runs_observed (the declared run history and the training logs found on the
     training box: both non-empty lists of the same length, under the iteration limit) and protocol_sha256; a missing,
     malformed or inconsistent field is recorded and the result is machine-not-assessable ("training provenance
     incomplete"), never accepted;
  5. applicability (version 2): every declared and every observed run carries a parseable start stamp at or after the
     protocol's freeze instant (applicability.training_started_after, training-box local time, second resolution), and the
     manifest's protocol_sha256 equals the hash of the protocol file this evaluator reads. A run started earlier, on the
     protocol day but before the instant, undated, or bound to another protocol revision is not assessable under version 2
     (external audit of b02dd3b, finding 1: a runs OBJECT instead of a list skipped both the date and the limit checks,
     and any hour of the protocol day passed).
A gate failure writes a report with every class machine-not-assessable and the reason, and exits 1.

Scoring: only band slices with pair status usable or usable-flagged; reference class 255 ineligible everywhere; metrics from
scripts/cryo_metrics.py and nowhere else. Two kinds of controls, kept apart:
  evaluator sanity  perturbations of the REFERENCE scored against the reference (mirror, +3 px shift, 3 px dilation) must
                    degrade by the tolerances for every class with support; else the evaluator is not trusted and every
                    class is machine-not-assessable with that reason.
  model-side        the same perturbations of the PREDICTION, and the wrong-neighbour baseline (Denver labels 10 mm away,
                    compared with the model on exactly the same eligible slices). A model-side control that does not
                    behave as required makes THAT class machine-failed with the control named.
Per class the report keeps every run diagnostic of the surface metric (per_run, support, false-positive runs) and per-band
prediction / reference / false-positive voxel counts and reference-bearing slice counts.

Statuses per class: machine-accepted / machine-failed (reason) / machine-not-assessable (reason). Nothing is anatomy.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cryo_metrics_v2 as M  # noqa: E402

BANDS = ROOT / 'registry/cryo-eval-bands-v1.json'
PROTOCOL = ROOT / 'registry/machine-acceptance-protocol-v2.json'
TMAP = ROOT / 'registry/cryo-tissue-map.json'
CLASSES_REPORT = ROOT / 'generated/cryo-tissue-classes-block2.json'
PAIRED = ('usable', 'usable-flagged')
IGNORE = 255
TRAIN_FIELDS = ('training_slices_k', 'weights_sha256', 'nnunetv2_version', 'dataset_fingerprint', 'plans_identifier', 'seed', 'fold', 'runs', 'runs_observed', 'protocol_sha256')


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()


def rel(p):
    p = Path(p).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def score(pred, ref, elig, runs, k_first):
    # version 2: the masks reach the surface metric UNRESTRICTED; Dice restricts to eligibility itself
    return {'dice': M.dice(pred, ref, elig), **M.surface_p95(pred, ref, elig, runs, k_first)}


def run_registry_validator():
    spec = importlib.util.spec_from_file_location('vcp', ROOT / 'scripts/validate-cryo-pilot.py')
    V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
    import io, contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            V.main()
    except SystemExit as e:
        return False, str(e)
    return True, buf.getvalue().strip()


def identity_gate(block, prot):
    fx = prot['identity_by_hash']['fixed_now']
    actual = {
        'rgb_block_manifest_sha256': sha_file(block / 'manifest.json'),
        'tissue_classes_volume_sha256': sha_file(block / 'tissue-classes.nii.gz'),
        'tissue_classes_report_sha256': sha_file(CLASSES_REPORT),
        'eval_bands_sha256': sha_file(BANDS),
        'tissue_map_sha256': sha_file(TMAP),
        'noise_floor_sha256': sha_file(ROOT / 'generated/denver-noise-floor.json'),
        'surface_floor_sha256': sha_file(ROOT / 'generated/denver-surface-floor-v2.json'),
        'metrics_sha256': sha_file(ROOT / 'scripts/cryo_metrics_v2.py'),
        'protocol_v1_sha256': sha_file(ROOT / 'registry/machine-acceptance-protocol-v1.json'),
        'evaluator_sha256': sha_file(__file__),
    }
    mism = [k for k, v in actual.items() if fx.get(k) != v]
    man = json.loads((block / 'manifest.json').read_text())
    if fx.get('rgb_volume_sha256') != man['outputs']['rgb_sha256']:
        mism.append('rgb_volume_sha256 (manifest)')
    return mism, actual


def prediction_gate(pimg, ref_img, allowed):
    problems = []
    if pimg.shape != ref_img.shape:
        problems.append(f'shape {pimg.shape} differs from the reference {ref_img.shape}')
    if not np.allclose(pimg.affine, ref_img.affine, atol=1e-6):
        problems.append('affine differs from the reference grid (translation, mirror or spacing)')
    dt = pimg.get_data_dtype()
    if not np.issubdtype(dt, np.integer):
        problems.append(f'dtype {dt} is not integral')
    raw = np.asarray(pimg.dataobj)
    if not np.issubdtype(raw.dtype, np.integer):
        if not np.isfinite(raw).all():
            problems.append('non-finite values')
        elif not np.array_equal(raw, np.rint(raw)):
            problems.append('fractional values')
    vals = set(int(v) for v in np.unique(raw))
    bad = sorted(vals - set(allowed))
    if bad:
        problems.append(f'label values outside the active output classes {allowed}: {bad[:10]}')
    return problems, raw


def _run_instant(started):
    """nnU-Net log stamps look like 2026_9_14_17_09_18 (training-box local time); ISO date-times are accepted too. Returns
    'YYYY-MM-DD HH:MM:SS' or None. A bare date has no time and is NOT accepted: the applicability rule is an instant."""
    import re
    m = re.match(r'^\s*(\d{4})[-_](\d{1,2})[-_](\d{1,2})[T _](\d{1,2})[:_](\d{1,2})[:_](\d{1,2})', str(started or ''))
    if not m:
        return None
    return '%04d-%02d-%02d %02d:%02d:%02d' % tuple(int(g) for g in m.groups())


def training_gate(train, bands, protocol):
    problems = []
    if train is None:
        return ['no --training-manifest given'], None
    for f in TRAIN_FIELDS:
        if f not in train or train[f] in (None, '', []):
            problems.append(f'training manifest field missing or empty: {f}')
    if problems:
        return problems, None
    te = bands['training_eligibility']
    primary = set(k for lo, hi in te['primary_k_ranges'] for k in range(lo, hi + 1))
    aux = set(k for lo, hi in te['auxiliary_k_ranges'] for k in range(lo, hi + 1))
    forbidden = set()
    for b in bands['bands']:
        forbidden.update(range(b['buffer_k'][0][0], b['buffer_k'][1][1] + 1))
    used = set(int(k) for k in train['training_slices_k'])
    if used & forbidden:
        problems.append(f'{len(used & forbidden)} training slices lie in a band or buffer')
    if used & aux:
        problems.append(f'{len(used & aux)} training slices lie in the auxiliary stratum (off under this protocol)')
    if used - primary:
        problems.append(f'{len(used - primary)} training slices outside the primary eligibility')
    if not used:
        problems.append('no training slices listed')
    limit = protocol['iteration_limit']['training_runs_per_variant']
    runs, observed = train['runs'], train['runs_observed']
    for name, lst in (('runs', runs), ('runs_observed', observed)):
        if not isinstance(lst, list) or not lst or not all(isinstance(r, dict) for r in lst):
            problems.append(f'{name} must be a non-empty list of run records (got {type(lst).__name__})')
    if problems:
        return problems, None
    if len(runs) > limit:
        problems.append(f'{len(runs)} runs exceed the iteration limit {limit}')
    if len(observed) != len(runs):
        problems.append(f'{len(runs)} runs declared against {len(observed)} training logs observed on the training box')
    # gate 5 (version 2): every declared and every observed run must have started at or after the instant this revision of
    # the protocol was frozen; a variant trained earlier was scored under version 1 and stays there. Second resolution:
    # the protocol day alone is not enough (audit of b02dd3b, finding 1).
    since = _run_instant(protocol['applicability']['training_started_after'])
    if since is None:
        problems.append('protocol applicability.training_started_after is not a parseable instant')
    else:
        for name, lst in (('declared run', runs), ('observed training log', observed)):
            for r in lst:
                started = str(r.get('started', ''))
                at = _run_instant(started)
                if at is None:
                    problems.append(f'{name} without a parseable start instant (version 2 applies only to runs started at or after {since})')
                elif at < since:
                    problems.append(f'{name} started {started} before the protocol freeze instant {since}: not assessable under version 2')
    # gate 5, revision: the manifest names the protocol revision it was written under; another revision is another protocol
    actual = sha_file(PROTOCOL)
    if str(train['protocol_sha256']).lower() != actual:
        problems.append(f'training manifest bound to protocol revision {str(train["protocol_sha256"])[:12]}, this evaluator reads {actual[:12]}')
    return problems, {'slices_used': len(used), 'primary_slices': len(primary), 'runs': len(runs), 'runs_observed': len(observed), 'protocol_sha256': actual}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--block', required=True)
    ap.add_argument('--prediction')
    ap.add_argument('--training-manifest')
    ap.add_argument('--oracle', action='store_true')
    ap.add_argument('--variant', default='oracle')
    ap.add_argument('--out')
    ap.add_argument('--note', default=None)
    a = ap.parse_args()
    t0 = time.time()
    block = Path(a.block)
    man = json.loads((block / 'manifest.json').read_text())
    bands = json.loads(BANDS.read_text())
    prot = json.loads(PROTOCOL.read_text())
    tmap = json.loads(TMAP.read_text())
    out = Path(a.out) if a.out else ROOT / 'generated' / ('cryo-pilot-%s-block%d.json' % ('oracle-controls-v2' if a.oracle else 'acceptance-v2-' + a.variant, man['block']['region']))
    names_not = prot['scope'].get('classes_not_assessable_by_construction', {})

    def refuse(reason, extra):
        classes = {c: {'class': c, 'status': 'machine-not-assessable', 'reason': reason} for c in prot['scope']['classes_assessed']}
        for c, why in names_not.items():
            if c != 'background':
                classes[c] = {'class': c, 'status': 'machine-not-assessable', 'reason': why}
        rep = {'id': 'cryo-pilot-acceptance-v2-block%d' % man['block']['region'], 'protocol_version': 2, 'variant': a.variant, 'oracle': a.oracle, 'date': time.strftime('%Y-%m-%d'), 'gate_failed': reason, **extra,
               'classes': classes, 'closure': {'machine-accepted': [], 'machine-failed': [], 'machine-not-assessable': sorted(classes)}, 'seconds': round(time.time() - t0, 1)}
        out.write_text(json.dumps(rep, indent=1))
        print(json.dumps({'done': False, 'gate_failed': reason, 'out': rel(out), **{k: v for k, v in extra.items() if k != 'identity_actual'}}))
        sys.exit(1)

    # gate 1: registry validator
    ok, msg = run_registry_validator()
    if not ok:
        refuse('registry validator failed', {'validator': msg})
    # gate 2: identity chain
    mism, actual = identity_gate(block, prot)
    if mism:
        refuse('inputs differ from the protocol identity_by_hash.fixed_now', {'identity_mismatch': mism, 'identity_actual': actual})
    ref_img = nib.load(str(block / 'tissue-classes.nii.gz'))
    ref = np.asarray(ref_img.dataobj)
    if ref.dtype != np.uint8:
        refuse('reference volume is not uint8', {})
    K = ref.shape[2]
    allowed = prot['training']['active_output_classes']
    train_info = None
    if a.oracle:
        pred = ref.copy(); pred_sha = 'oracle: prediction is the reference'
    else:
        if not a.prediction:
            refuse('no --prediction given', {})
        pimg = nib.load(a.prediction)
        problems, raw = prediction_gate(pimg, ref_img, allowed)
        if problems:
            refuse('prediction volume rejected', {'prediction_problems': problems, 'prediction': rel(a.prediction)})
        pred = raw.astype(np.uint8)
        pred_sha = sha_file(a.prediction)
        train = json.loads(Path(a.training_manifest).read_text()) if a.training_manifest else None
        problems, train_info = training_gate(train, bands, prot)
        if problems:
            refuse('training provenance incomplete or contaminated', {'training_problems': problems, 'training_manifest': rel(a.training_manifest) if a.training_manifest else None})
        train_info['manifest_sha256'] = sha_file(a.training_manifest)
        train_info.update({f: train[f] for f in TRAIN_FIELDS if f != 'training_slices_k'})

    k_first = man['block']['k_first']
    status = {r['k']: r['status'] for r in man['per_slice']}
    scoring_k = []
    for b in bands['bands']:
        scoring_k += [k for k in range(b['k_first'], b['k_last'] + 1) if status[k] in PAIRED]
    usable_k = [k for k in scoring_k if status[k] == 'usable']
    slice_elig = np.zeros(K, bool); slice_elig[[k - k_first for k in scoring_k]] = True
    slice_usable = np.zeros(K, bool); slice_usable[[k - k_first for k in usable_k]] = True
    E = (ref != IGNORE) & slice_elig[None, None, :]
    E_usable = (ref != IGNORE) & slice_usable[None, None, :]
    runs = [(b['k_first'], b['k_last']) for b in bands['bands']]
    ctrl = prot['negative_controls']
    shift_px, dil_px = ctrl['shift']['pixels'], ctrl['dilation']['pixels']
    mirror_margin = ctrl['mirror']['dice_margin']
    nb = ctrl['wrong_neighbour']['slices']

    ref_ignore = ref == IGNORE
    out_classes = {}
    evaluator_ok = True
    evaluator_notes = []
    for cname in prot['scope']['classes_assessed']:
        cval = next(c['value'] for c in tmap['classes'] if c['name'] == cname)
        crit = prot['criteria'][cname]
        R = ref == cval
        P = pred == cval
        support = int((R & E).sum())
        ref_slices = int((R & E).any(axis=(0, 1)).sum())
        row = {'class': cname, 'value': cval, 'reference_voxels_on_scoring_slices': support, 'reference_bearing_slices': ref_slices, 'min_reference_voxels': crit['min_reference_voxels']}
        if support < crit['min_reference_voxels']:
            row['status'] = 'machine-not-assessable'; row['reason'] = 'reference support below the minimum'
            out_classes[cname] = row; continue
        base = score(P, R, E, runs, k_first)
        row['pooled'] = base
        row['usable_only'] = score(P, R, E_usable, runs, k_first)
        row['per_band'] = {}
        for b in bands['bands']:
            Eb = E.copy(); Eb[:, :, :b['k_first'] - k_first] = False; Eb[:, :, b['k_last'] - k_first + 1:] = False
            row['per_band'][str(b['band'])] = {'reference_voxels': int((R & Eb).sum()), 'prediction_voxels': int((P & Eb).sum()), 'false_positive_voxels': int((P & ~R & Eb).sum()),
                                               'false_negative_voxels': int((R & ~P & Eb).sum()), 'reference_bearing_slices': int((R & Eb).any(axis=(0, 1)).sum()),
                                               'prediction_bearing_slices': int((P & Eb).any(axis=(0, 1)).sum()), **score(P, R, Eb, [(b['k_first'], b['k_last'])], k_first)}
        ref_self = {'dice': 1.0, 'p95_mm': 0.0}
        san = {}
        for nm, pert in (('mirror', M.mirror_i(R)), ('shift', M.shift_i(R, shift_px)), ('dilation', M.dilate_inplane(R, dil_px))):
            s = score(pert, R, E, runs, k_first)
            deg = M.degrades(ref_self, s)
            san[nm] = {**s, 'degrades': deg}
            if deg['dice'] is not True or deg['p95'] is not True:
                evaluator_ok = False; evaluator_notes.append(f'{cname}: reference control {nm} did not degrade')
        row['evaluator_sanity_on_reference'] = san
        model_ctrl = {}
        for nm, pert in (('mirror', M.mirror_i(P)), ('shift', M.shift_i(P, shift_px)), ('dilation', M.dilate_inplane(P, dil_px))):
            s = score(pert, R, E, runs, k_first)
            deg = M.degrades(base, s)
            if nm == 'mirror':
                ok = (s['dice'] is not None and base['dice'] is not None and s['dice'] <= base['dice'] - mirror_margin) if cname in ctrl['mirror']['classes'] else None
            else:
                ok = bool(deg['dice'] is True and deg['p95'] is True) if base['p95_mm'] is not None else deg['dice']
            model_ctrl[nm] = {**s, 'degrades': deg, 'as_required': ok}
        nb_pred = np.zeros_like(R); En = np.zeros_like(E)
        for b in bands['bands']:
            for k in range(b['k_first'], b['k_last'] + 1):
                kn = k + nb
                if kn <= b['k_last'] and status[k] in PAIRED and status[kn] in PAIRED:
                    nb_pred[:, :, k - k_first] = R[:, :, kn - k_first]
                    En[:, :, k - k_first] = E[:, :, k - k_first]
        s_nb = score(nb_pred, R, En, runs, k_first)
        s_model_same = score(P, R, En, runs, k_first)
        nb_ok = (s_model_same['dice'] is not None and s_nb['dice'] is not None and s_model_same['dice'] >= s_nb['dice'] + M.DICE_TOL)
        model_ctrl['wrong_neighbour'] = {'neighbour_slices_mm': round(nb * M.SPACING[2], 3), 'matched_slices': int(En.any(axis=(0, 1)).sum()), 'neighbour': s_nb, 'model_on_same_slices': s_model_same, 'as_required': bool(nb_ok)}
        row['model_side_controls'] = model_ctrl
        # version 2 reported term: predicted volume on ignore, per band, never scored
        row['predicted_volume_on_ignore'] = {}
        for b in bands['bands']:
            sb = np.zeros(K, bool); sb[[k - k_first for k in scoring_k if b['k_first'] <= k <= b['k_last']]] = True
            row['predicted_volume_on_ignore'][str(b['band'])] = {'voxels': M.volume_on_ignore(P, ref_ignore, sb), 'ml': round(M.volume_on_ignore(P, ref_ignore, sb) * M.SPACING[0] * M.SPACING[1] * M.SPACING[2] / 1000.0, 3)}
        # version 2 criterion for classes with a required neighbour: distance from predicted class to predicted neighbour, blind to ignore
        fails = []
        if crit.get('required_neighbour'):
            nb_name = crit['required_neighbour']['class']
            nb_val = next(c['value'] for c in tmap['classes'] if c['name'] == nb_name)
            rn = M.required_neighbour_distance(P, pred == nb_val, slice_elig)
            rn_ref = M.required_neighbour_distance(R, ref == nb_val, slice_elig)
            row['required_neighbour'] = {'class': nb_name, 'prediction': rn, 'reference_same_figure': rn_ref, 'median_mm_max': crit['required_neighbour']['median_mm_max']}
            if rn['median_mm'] is None or rn['median_mm'] > crit['required_neighbour']['median_mm_max']:
                fails.append('required neighbour %s: median distance %s above %.4f mm (%s)' % (nb_name, 'undefined' if rn['median_mm'] is None else '%.4f' % rn['median_mm'], crit['required_neighbour']['median_mm_max'], rn['status']))
        if crit.get('dice_min') is not None and (base['dice'] is None or base['dice'] < crit['dice_min']):
            fails.append('dice below %.4f' % crit['dice_min'])
        if crit.get('surface_p95_mm_max') is not None and (base['p95_mm'] is None or base['p95_mm'] > crit['surface_p95_mm_max']):
            fails.append('surface p95 above %.4f mm (%s)' % (crit['surface_p95_mm_max'], base['status']))
        for nm, c in model_ctrl.items():
            if c['as_required'] is False:
                fails.append(f'model-side control {nm} not as required')
        row['status'] = 'machine-failed' if fails else 'machine-accepted'
        row['reason'] = '; '.join(fails) if fails else 'every criterion and control as required'
        out_classes[cname] = row
    if not evaluator_ok:
        for r in out_classes.values():
            r['status'] = 'machine-not-assessable'; r['reason'] = 'evaluator sanity control failed: ' + '; '.join(evaluator_notes)
    for cname, why in names_not.items():
        if cname != 'background':
            out_classes[cname] = {'class': cname, 'status': 'machine-not-assessable', 'reason': why}
    report = {
        'id': 'cryo-pilot-acceptance-v2-block%d' % man['block']['region'], 'protocol_version': 2, 'variant': a.variant, 'oracle': a.oracle, 'date': time.strftime('%Y-%m-%d'), 'note': a.note,
        'gates': {'registry_validator': msg, 'identity_chain': 'matched', 'prediction_grid_and_values': 'oracle' if a.oracle else 'accepted', 'training_provenance': 'oracle' if a.oracle else 'accepted',
                  'applicability_by_training_date': 'oracle' if a.oracle else 'accepted'},
        'protocol': {'file': rel(PROTOCOL), 'version': prot['version'], 'sha256': sha_file(PROTOCOL)},
        'identity': {**actual, 'prediction_sha256': pred_sha, 'training': train_info},
        'scoring': {'slices': len(scoring_k), 'usable_only_slices': len(usable_k), 'runs_k': runs, 'eligible_voxels': int(E.sum())},
        'evaluator_trusted': evaluator_ok, 'evaluator_notes': evaluator_notes,
        'classes': out_classes,
        'closure': {s: [c for c, r in out_classes.items() if r['status'] == s] for s in ('machine-accepted', 'machine-failed', 'machine-not-assessable')},
        'limits': prot['limits'] + ['protocol version 2 was written after the version 1 scores were known; it grades only variants trained after its date',
                                    'class-level concordance with Denver original labels on the frozen bands; never anatomical accuracy; never validation',
                                    'the surface guarantee is per run: a small omitted component inside a run with a correctly predicted component is not detected as emptiness'],
        'seconds': round(time.time() - t0, 1),
    }
    out.write_text(json.dumps(report, indent=1))
    brief = {c: {'status': r['status'], 'dice': r.get('pooled', {}).get('dice'), 'p95': r.get('pooled', {}).get('p95_mm'),
                 'ctrl_dice': {k: v.get('dice') for k, v in r.get('model_side_controls', {}).items() if k != 'wrong_neighbour'},
                 'neighbour_dice': r.get('model_side_controls', {}).get('wrong_neighbour', {}).get('neighbour', {}).get('dice')} for c, r in out_classes.items()}
    print(json.dumps({'done': True, 'out': rel(out), 'evaluator_trusted': evaluator_ok, 'classes': brief, 'seconds': report['seconds']}))


if __name__ == '__main__':
    main()
