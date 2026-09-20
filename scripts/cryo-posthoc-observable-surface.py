"""Post hoc analysis of the pilot's surface error with the observable-boundary metric of scripts/cryo_posthoc_surface.py.

  .venv/bin/python scripts/cryo-posthoc-observable-surface.py --block data/derived/nlm-vhf/cryosections/block2 \
      --variant rgb-only=data/derived/nnunet/pred/pred-block2-rgb-only.nii.gz \
      --variant rgb-plus-ct-prior=data/derived/nnunet/pred/pred-block2-rgb-plus-ct-prior.nii.gz

This is NOT an acceptance evaluation. It was written on 2026-09-20 after both variants had been scored under
protocol v1, so it can neither accept nor fail anything, and it changes no status. It reports, for every
class and variant: the v1 pooled figures copied from the acceptance report (bound by hash), the post hoc
p95 with its support and both directions, the same three evaluator-sanity perturbations of the reference,
the same three model-side perturbations of the prediction and the wrong-neighbour baseline, all under the
post hoc metric, so that the reader can see whether the new metric discriminates where v1 did not. The v1
thresholds are quoted next to the figures for orientation only. Output: one JSON with post_hoc: true.
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
import cryo_metrics as V1  # noqa: E402  (perturbations and tolerances only; the v1 metric itself is read from the reports)
import cryo_posthoc_surface as PH  # noqa: E402

BANDS = ROOT / 'registry/cryo-eval-bands-v1.json'
PROTOCOL = ROOT / 'registry/machine-acceptance-protocol-v1.json'
TMAP = ROOT / 'registry/cryo-tissue-map.json'
PAIRED = ('usable', 'usable-flagged')
IGNORE = 255


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()


def rel(p):
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def degrades_p95(base, pert):
    if base.get('p95_mm') is None or pert.get('p95_mm') is None:
        return None
    return bool(pert['p95_mm'] >= base['p95_mm'] + V1.P95_TOL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--block', required=True)
    ap.add_argument('--variant', action='append', required=True, help='name=prediction.nii.gz')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    t0 = time.time()
    block = Path(a.block)
    man = json.loads((block / 'manifest.json').read_text())
    bands = json.loads(BANDS.read_text())
    prot = json.loads(PROTOCOL.read_text())
    tmap = json.loads(TMAP.read_text())
    region = man['block']['region']
    out = Path(a.out) if a.out else ROOT / 'generated' / f'cryo-posthoc-observable-surface-block{region}.json'
    ref_img = nib.load(str(block / 'tissue-classes.nii.gz'))
    ref = np.asarray(ref_img.dataobj)
    K = ref.shape[2]
    k_first = man['block']['k_first']
    status = {r['k']: r['status'] for r in man['per_slice']}
    scoring_k = [k for b in bands['bands'] for k in range(b['k_first'], b['k_last'] + 1) if status[k] in PAIRED]
    slice_elig = np.zeros(K, bool); slice_elig[[k - k_first for k in scoring_k]] = True
    E = (ref != IGNORE) & slice_elig[None, None, :]
    runs = [(b['k_first'], b['k_last']) for b in bands['bands']]
    ctrl = prot['negative_controls']
    shift_px, dil_px, nb = ctrl['shift']['pixels'], ctrl['dilation']['pixels'], ctrl['wrong_neighbour']['slices']

    variants = {}
    for spec in a.variant:
        name, path = spec.split('=', 1)
        pimg = nib.load(path)
        assert pimg.shape == ref_img.shape and np.allclose(pimg.affine, ref_img.affine, atol=1e-6), 'prediction grid differs from the reference'
        acc_path = ROOT / 'generated' / f'cryo-pilot-acceptance-block{region}-{name}.json'
        acc = json.loads(acc_path.read_text())
        assert acc['identity']['prediction_sha256'] == sha_file(path), f'{name}: prediction hash differs from its v1 acceptance report'
        variants[name] = {'prediction': rel(path), 'prediction_sha256': acc['identity']['prediction_sha256'],
                          'v1_acceptance_report': rel(acc_path), 'v1_acceptance_sha256': sha_file(acc_path),
                          'pred': np.asarray(pimg.dataobj).astype(np.uint8), 'acc': acc}

    classes = {}
    for cname in prot['scope']['classes_assessed']:
        cval = next(c['value'] for c in tmap['classes'] if c['name'] == cname)
        crit = prot['criteria'][cname]
        R = ref == cval
        row = {'class': cname, 'value': cval, 'v1_surface_p95_mm_max_for_orientation_only': crit.get('surface_p95_mm_max')}
        san = {}
        ref_self = {'p95_mm': 0.0}
        for nm, pert in (('mirror', V1.mirror_i(R)), ('shift', V1.shift_i(R, shift_px)), ('dilation', V1.dilate_inplane(R, dil_px))):
            s = PH.observable_surface_p95(pert, R, E, runs, k_first)
            san[nm] = {k: s.get(k) for k in ('p95_mm', 'p50_mm', 'mean_mm', 'n_distances', 'status')}
            san[nm]['degrades_p95'] = degrades_p95(ref_self, s)
        row['evaluator_sanity_on_reference'] = san
        row['variants'] = {}
        for vname, v in variants.items():
            P = v['pred'] == cval
            base = PH.observable_surface_p95(P, R, E, runs, k_first)
            acc_row = v['acc']['classes'][cname]
            per_band = {}
            for b in bands['bands']:
                per_band[str(b['band'])] = PH.observable_surface_p95(P, R, E, [(b['k_first'], b['k_last'])], k_first)
            mc = {}
            for nm, pert in (('mirror', V1.mirror_i(P)), ('shift', V1.shift_i(P, shift_px)), ('dilation', V1.dilate_inplane(P, dil_px))):
                s = PH.observable_surface_p95(pert, R, E, runs, k_first)
                mc[nm] = {k: s.get(k) for k in ('p95_mm', 'p50_mm', 'mean_mm', 'n_distances', 'status')}
                mc[nm]['degrades_p95'] = degrades_p95(base, s)
            nb_pred = np.zeros_like(R); En = np.zeros_like(E)
            for b in bands['bands']:
                for k in range(b['k_first'], b['k_last'] + 1):
                    kn = k + nb
                    if kn <= b['k_last'] and status[k] in PAIRED and status[kn] in PAIRED:
                        nb_pred[:, :, k - k_first] = R[:, :, kn - k_first]
                        En[:, :, k - k_first] = E[:, :, k - k_first]
            s_nb = PH.observable_surface_p95(nb_pred, R, En, runs, k_first)
            s_same = PH.observable_surface_p95(P, R, En, runs, k_first)
            mc['wrong_neighbour'] = {'neighbour_p95_mm': s_nb.get('p95_mm'), 'neighbour_p50_mm': s_nb.get('p50_mm'), 'model_on_same_slices_p95_mm': s_same.get('p95_mm'),
                                     'model_on_same_slices_p50_mm': s_same.get('p50_mm'),
                                     'model_beats_neighbour_p95': (s_nb.get('p95_mm') is not None and s_same.get('p95_mm') is not None and s_same['p95_mm'] <= s_nb['p95_mm'] - V1.P95_TOL)}
            row['variants'][vname] = {
                'v1_status': acc_row['status'], 'v1_reason': acc_row.get('reason'),
                'v1_pooled': {k: acc_row.get('pooled', {}).get(k) for k in ('dice', 'p95_mm', 'mean_mm', 'n_distances', 'status', 'support')},
                'post_hoc': base, 'post_hoc_per_band': per_band, 'model_side_controls_post_hoc': mc}
        classes[cname] = row

    report = {
        'id': f'cryo-posthoc-observable-surface-block{region}', 'date': time.strftime('%Y-%m-%d'), 'post_hoc': True,
        'statement': ('Post hoc analysis written on 2026-09-20 after both variants were scored under protocol v1. It accepts nothing, fails nothing '
                      'and changes no status; the v1 results quoted here stand on the record. The metric is scripts/cryo_posthoc_surface.py '
                      '(observable boundaries -> full boundaries, faces removed, ignore never a source). Nothing here is anatomy.'),
        'metric': {'file': rel(ROOT / 'scripts/cryo_posthoc_surface.py'), 'sha256': sha_file(ROOT / 'scripts/cryo_posthoc_surface.py'),
                   'tests': rel(ROOT / 'scripts/test-cryo-posthoc-surface.py'), 'analysis_script_sha256': sha_file(__file__)},
        'v1': {'protocol': rel(PROTOCOL), 'protocol_sha256': sha_file(PROTOCOL), 'metrics_sha256': sha_file(ROOT / 'scripts/cryo_metrics.py')},
        'inputs': {'reference_sha256': sha_file(block / 'tissue-classes.nii.gz'), 'bands_sha256': sha_file(BANDS),
                   'variants': {n: {k: v[k] for k in ('prediction', 'prediction_sha256', 'v1_acceptance_report', 'v1_acceptance_sha256')} for n, v in variants.items()}},
        'scoring': {'slices': len(scoring_k), 'runs_k': runs, 'eligible_voxels': int(E.sum()), 'shift_px': shift_px, 'dilation_px': dil_px, 'neighbour_slices': nb, 'p95_tolerance_mm': V1.P95_TOL},
        'classes': classes,
        'limits': ['post hoc: the metric was designed knowing the v1 scores and the direction of the artefact; it cannot serve as an acceptance criterion for these two variants',
                   'a prediction boundary against ignore is counted, never measured: over- or under-extension of a class into unlabelled tissue is invisible to the distances',
                   'the reference surface is taken as fully observed because Denver labels each structure completely; a structure Denver omitted is not in the reference and its boundary is unknown',
                   'class-level concordance with Denver original labels on the frozen bands; never anatomical accuracy; never validation'],
        'seconds': round(time.time() - t0, 1),
    }
    out.write_text(json.dumps(report, indent=1))
    brief = {c: {v: {'v1_p95': r['variants'][v]['v1_pooled']['p95_mm'], 'post_hoc_p95': r['variants'][v]['post_hoc'].get('p95_mm'),
                     'shift_degrades': r['variants'][v]['model_side_controls_post_hoc']['shift']['degrades_p95']} for v in r['variants']} for c, r in classes.items()}
    print(json.dumps({'done': True, 'out': rel(out), 'classes': brief, 'seconds': report['seconds']}))


if __name__ == '__main__':
    main()
