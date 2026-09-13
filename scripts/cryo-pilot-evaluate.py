"""Evaluator of the cryosection pilot against the frozen bands and the pre-registered protocol (plan B stage 6, 2.7).

  .venv/bin/python scripts/cryo-pilot-evaluate.py --block data/derived/nlm-vhf/cryosections/block2 \
      --prediction PRED.nii.gz --variant rgb-only --out generated/cryo-pilot-acceptance-block2-rgb-only.json [--weights-sha SHA ...]
  .venv/bin/python scripts/cryo-pilot-evaluate.py --block ... --oracle      # prediction := reference; freezes the evaluator sanity figures

Inputs: tissue-classes.nii.gz of the block (reference, from registry/cryo-tissue-map.json), the manifest (slice statuses),
registry/cryo-eval-bands-v1.json (scoring slices), registry/machine-acceptance-protocol-v1.json (criteria, controls,
hashes), and a prediction volume (i, j, K) uint8 with the same class ids over the whole block. Only band slices with pair
status usable or usable-flagged are scored; class 255 of the reference is ineligible everywhere. Metrics come from
scripts/cryo_metrics.py and nowhere else.

Two kinds of controls, kept apart (Codex audit of afec927, P2):
  evaluator sanity  perturbations of the REFERENCE scored against the reference (mirror, +3 px shift, 3 px dilation) must
                    degrade by the tolerances for every class with support; if one does not, the evaluator is not trusted
                    and every class is machine-not-assessable with that reason.
  model-side        the same perturbations of the PREDICTION, and the wrong-neighbour baseline (Denver labels 10 mm away,
                    compared with the model on exactly the same eligible slices). A model-side control that does not
                    behave as required makes THAT class machine-failed with the control named; other classes are untouched.

Statuses per class: machine-accepted / machine-failed (reason) / machine-not-assessable (reason). Nothing is anatomy.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cryo_metrics as M  # noqa: E402

BANDS = ROOT / 'registry/cryo-eval-bands-v1.json'
PROTOCOL = ROOT / 'registry/machine-acceptance-protocol-v1.json'
TMAP = ROOT / 'registry/cryo-tissue-map.json'
PAIRED = ('usable', 'usable-flagged')
IGNORE = 255


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def score(pred, ref, elig, runs, k_first):
    return {'dice': M.dice(pred, ref, elig), **{k: v for k, v in M.surface_p95(pred, ref, elig, runs, k_first).items() if k != 'per_run'}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--block', required=True)
    ap.add_argument('--prediction')
    ap.add_argument('--oracle', action='store_true')
    ap.add_argument('--variant', default='oracle')
    ap.add_argument('--out')
    ap.add_argument('--weights-sha', default=None)
    ap.add_argument('--note', default=None)
    a = ap.parse_args()
    t0 = time.time()
    block = Path(a.block)
    man = json.loads((block / 'manifest.json').read_text())
    bands = json.loads(BANDS.read_text())
    prot = json.loads(PROTOCOL.read_text())
    tmap = json.loads(TMAP.read_text())
    k_first = man['block']['k_first']
    ref_img = nib.load(str(block / 'tissue-classes.nii.gz'))
    ref = np.asarray(ref_img.dataobj).astype(np.uint8)
    K = ref.shape[2]
    status = {r['k']: r['status'] for r in man['per_slice']}
    if a.oracle:
        pred = ref.copy(); pred_sha = 'oracle: prediction is the reference'
    else:
        pimg = nib.load(a.prediction)
        pred = np.asarray(pimg.dataobj).astype(np.uint8)
        if pred.shape != ref.shape:
            raise SystemExit(f'prediction shape {pred.shape} differs from the block {ref.shape}')
        pred_sha = sha_file(a.prediction)

    # eligibility
    scoring_k = []
    for b in bands['bands']:
        scoring_k += [k for k in range(b['k_first'], b['k_last'] + 1) if status[k] in PAIRED]
    usable_k = [k for k in scoring_k if status[k] == 'usable']
    slice_elig = np.zeros(K, bool); slice_elig[[k - k_first for k in scoring_k]] = True
    slice_usable = np.zeros(K, bool); slice_usable[[k - k_first for k in usable_k]] = True
    E = (ref != IGNORE) & slice_elig[None, None, :]
    E_usable = (ref != IGNORE) & slice_usable[None, None, :]
    runs = [(b['k_first'], b['k_last']) for b in bands['bands']]
    names = {c['value']: c['name'] for c in tmap['classes']}
    ctrl = prot['negative_controls']
    shift_px, dil_px = ctrl['shift']['pixels'], ctrl['dilation']['pixels']
    mirror_margin = ctrl['mirror']['dice_margin']
    nb = ctrl['wrong_neighbour']['slices']

    out_classes = {}
    evaluator_ok = True
    evaluator_notes = []
    for cname in prot['scope']['classes_assessed']:
        cval = next(c['value'] for c in tmap['classes'] if c['name'] == cname)
        crit = prot['criteria'][cname]
        R = ref == cval
        P = pred == cval
        support = int((R & E).sum())
        row = {'class': cname, 'value': cval, 'reference_voxels_on_scoring_slices': support, 'min_reference_voxels': crit['min_reference_voxels']}
        if support < crit['min_reference_voxels']:
            row['status'] = 'machine-not-assessable'; row['reason'] = 'reference support below the minimum'
            out_classes[cname] = row; continue
        base = score(P, R, E, runs, k_first)
        row['pooled'] = base
        row['usable_only'] = score(P, R, E_usable, runs, k_first)
        row['per_band'] = {}
        for b in bands['bands']:
            Eb = E.copy(); Eb[:, :, :b['k_first'] - k_first] = False; Eb[:, :, b['k_last'] - k_first + 1:] = False
            row['per_band'][str(b['band'])] = {'reference_voxels': int((R & Eb).sum()), **score(P, R, Eb, [(b['k_first'], b['k_last'])], k_first)}
        # evaluator sanity: reference perturbed against reference
        ref_self = {'dice': 1.0, 'p95_mm': 0.0}
        san = {}
        for nm, pert in (('mirror', M.mirror_i(R)), ('shift', M.shift_i(R, shift_px)), ('dilation', M.dilate_inplane(R, dil_px))):
            s = score(pert, R, E, runs, k_first)
            deg = M.degrades(ref_self, s)
            san[nm] = {**s, 'degrades': deg}
            if deg['dice'] is not True or deg['p95'] is not True:
                evaluator_ok = False; evaluator_notes.append(f'{cname}: reference control {nm} did not degrade')
        row['evaluator_sanity_on_reference'] = san
        # model-side controls
        model_ctrl = {}
        for nm, pert in (('mirror', M.mirror_i(P)), ('shift', M.shift_i(P, shift_px)), ('dilation', M.dilate_inplane(P, dil_px))):
            s = score(pert, R, E, runs, k_first)
            deg = M.degrades(base, s)
            if nm == 'mirror':
                ok = (s['dice'] is not None and base['dice'] is not None and s['dice'] <= base['dice'] - mirror_margin) if cname in ctrl['mirror']['classes'] else None
            else:
                ok = bool(deg['dice'] is True and deg['p95'] is True) if base['p95_mm'] is not None else deg['dice']
            model_ctrl[nm] = {**s, 'degrades': deg, 'as_required': ok}
        # wrong neighbour on matched support
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
        # criteria
        fails = []
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
    for cname in prot['scope'].get('classes_not_assessable_by_construction', {}):
        if cname == 'background':
            continue
        out_classes[cname] = {'class': cname, 'status': 'machine-not-assessable', 'reason': prot['scope']['classes_not_assessable_by_construction'][cname]}
    report = {
        'id': 'cryo-pilot-acceptance-block%d' % man['block']['region'], 'variant': a.variant, 'oracle': a.oracle, 'date': time.strftime('%Y-%m-%d'), 'note': a.note,
        'protocol': {'file': str(PROTOCOL.relative_to(ROOT)), 'version': prot['version'], 'sha256': sha_file(PROTOCOL)},
        'identity': {'manifest_sha256': sha_file(block / 'manifest.json'), 'reference_sha256': sha_file(block / 'tissue-classes.nii.gz'), 'bands_sha256': sha_file(BANDS), 'tissue_map_sha256': sha_file(TMAP),
                     'metrics_sha256': sha_file(ROOT / 'scripts/cryo_metrics.py'), 'evaluator_sha256': sha_file(__file__), 'prediction_sha256': pred_sha, 'weights_sha256': a.weights_sha},
        'scoring': {'slices': len(scoring_k), 'usable_only_slices': len(usable_k), 'runs_k': runs, 'eligible_voxels': int(E.sum())},
        'evaluator_trusted': evaluator_ok, 'evaluator_notes': evaluator_notes,
        'classes': out_classes,
        'closure': {s: [c for c, r in out_classes.items() if r['status'] == s] for s in ('machine-accepted', 'machine-failed', 'machine-not-assessable')},
        'limits': prot['limits'] + ['class-level concordance with Denver original labels on the frozen bands; never anatomical accuracy; never validation'],
        'seconds': round(time.time() - t0, 1),
    }
    out = Path(a.out) if a.out else ROOT / 'generated' / ('cryo-pilot-%s-block%d.json' % ('oracle-controls' if a.oracle else 'acceptance-' + a.variant, man['block']['region']))
    out.write_text(json.dumps(report, indent=1))
    brief = {c: {'status': r['status'], 'dice': r.get('pooled', {}).get('dice'), 'p95': r.get('pooled', {}).get('p95_mm'),
                 'ctrl_dice': {k: v.get('dice') for k, v in r.get('model_side_controls', {}).items() if k != 'wrong_neighbour'},
                 'neighbour_dice': r.get('model_side_controls', {}).get('wrong_neighbour', {}).get('neighbour', {}).get('dice')} for c, r in out_classes.items()}
    print(json.dumps({'done': True, 'out': str(out.relative_to(ROOT)), 'evaluator_trusted': evaluator_ok, 'classes': brief, 'seconds': report['seconds']}))


if __name__ == '__main__':
    main()
