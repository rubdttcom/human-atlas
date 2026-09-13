"""Reserved evaluation bands for the cryosection pilot (plan B 2.4): machine-chosen, seeded, frozen before training.

Writes registry/cryo-eval-bands-v1.json from the RGB block manifest (slice statuses), the Denver label slab and the tissue
map. The machine draws the bands; nobody draws a reference (no anatomist). Rules, all in the file:

  band      50 mm of Denver slices (150 slices at 0.333 mm), scored against Denver's ORIGINAL labels through the tissue map
  buffer    10 mm (30 slices) on both sides of every band: neither training nor evaluation nor pseudo-labelling
  content   a candidate band is accepted only if at least --min-paired-fraction of its slices carry a photograph
            (status usable or usable-flagged); the mid-thigh start of the pelvis block is almost entirely excluded-identity
            and would otherwise yield an empty band
  spacing   bands, with their buffers, lie inside the block and do not overlap each other
  draw      candidate starts on a 1 mm grid; numpy default_rng(seed) draws uniformly among the candidates that still satisfy
            every rule; the number of candidates left at each draw is recorded
  freeze    the file records the SHA-256 of the manifest (RGB volume, labels, transform, pairs), of the tissue map and of the
            label slab it was drawn from; the stage 2 training-set builder must refuse a training set
            whose manifest hash differs, and the acceptance protocol (registry/machine-acceptance-protocol-v1.json) binds to
            this file's hash

Per band the file lists the slices by status, the Denver voxels per tissue class on the scoring slices (usable and
usable-flagged only) and the training complement (block minus bands minus buffers).

Training eligibility (Codex audit of 4da4b5b, point A, decided 13 September 2026 before any training): the complement is
split by supervision density. A 50 mm bin of the block (aligned to k_first) is `sparsely-supervised` when the median
ignore fraction of the body over its paired slices (generated/cryo-tissue-classes-block2.json) exceeds --sparse-ignore
(0.95): there Denver labels only the psoas. Primary training = paired complement slices in dense bins; auxiliary stratum =
paired complement slices in sparse bins (declared, off by default, a separate decision to use); excluded slices are never
sampled. Both counts are recorded; the bands are not redrawn. This is a label-density rule, not an anatomical boundary.
Nothing here is anatomy.

  .venv/bin/python scripts/select-cryo-eval-bands.py [--seed 20260913 --bands 2 --band-mm 50 --buffer-mm 10]
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'generated/cryosection-rgb-block2-manifest.json'
LABELS = ROOT / 'data/derived/denver/label-blocks/block2-k2285-3532-labels.npz'
TMAP = ROOT / 'registry/cryo-tissue-map.json'
OUT = ROOT / 'registry/cryo-eval-bands-v1.json'
PAIRED = ('usable', 'usable-flagged')


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ranges(ks):
    out, start, prev = [], None, None
    for k in ks:
        if start is None:
            start = prev = k; continue
        if k == prev + 1:
            prev = k; continue
        out.append([start, prev]); start = prev = k
    if start is not None:
        out.append([start, prev])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', default=str(MANIFEST))
    ap.add_argument('--labels', default=str(LABELS))
    ap.add_argument('--tissue-map', default=str(TMAP))
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--seed', type=int, default=20260913)
    ap.add_argument('--bands', type=int, default=2)
    ap.add_argument('--band-mm', type=float, default=50.0)
    ap.add_argument('--buffer-mm', type=float, default=10.0)
    ap.add_argument('--min-paired-fraction', type=float, default=0.70)
    ap.add_argument('--classes-report', default=str(ROOT / 'generated/cryo-tissue-classes-block2.json'))
    ap.add_argument('--sparse-ignore', type=float, default=0.95)
    a = ap.parse_args()
    man = json.loads(Path(a.manifest).read_text())
    tmap = json.loads(Path(a.tissue_map).read_text())
    cls_of = {r['value']: r['class'] for r in tmap['labels']}
    cls_name = {c['value']: c['name'] for c in tmap['classes']}
    z = np.load(a.labels, allow_pickle=False)
    labels = z['labels']
    lmeta = json.loads(str(z['meta']))
    k_first, k_last = man['block']['k_first'], man['block']['k_last']
    if (lmeta['k_first'], lmeta['k_last']) != (k_first, k_last):
        raise SystemExit('label slab and manifest cover different blocks')
    status = {r['k']: r['status'] for r in man['per_slice']}
    dz = man['grid']['spacing_mm_ijk'][2]
    band_n = int(round(a.band_mm / dz))
    buf_n = int(round(a.buffer_mm / dz))
    step = int(round(1.0 / dz))
    ks = list(range(k_first, k_last + 1))
    paired = np.array([status[k] in PAIRED for k in ks])

    def ok(start, taken):
        lo, hi = start - buf_n, start + band_n + buf_n - 1
        if lo < k_first or hi > k_last:
            return False
        if any(not (hi < t_lo or lo > t_hi) for t_lo, t_hi in taken):
            return False
        frac = paired[start - k_first:start - k_first + band_n].mean()
        return frac >= a.min_paired_fraction

    rng = np.random.default_rng(a.seed)
    taken, bands, draws = [], [], 0
    all_starts = list(range(k_first, k_last - band_n + 2, step))
    for b in range(a.bands):
        cands = [s for s in all_starts if ok(s, taken)]
        if not cands:
            raise SystemExit(f'no candidate start for band {b + 1} under the rules')
        s = int(rng.choice(cands)); draws += 1
        lo, hi = s, s + band_n - 1
        taken.append([lo - buf_n, hi + buf_n])
        sl = labels[lo - k_first:hi - k_first + 1]
        score_mask = np.array([status[k] in PAIRED for k in range(lo, hi + 1)])
        counts = np.bincount(sl[score_mask].ravel(), minlength=256) if score_mask.any() else np.zeros(256, int)
        per_class = {}
        for v, c in enumerate(counts):
            if c and v != 0:
                nm = cls_name[cls_of[v]]
                per_class[nm] = per_class.get(nm, 0) + int(c)
        st = {}
        for k in range(lo, hi + 1):
            st[status[k]] = st.get(status[k], 0) + 1
        bands.append({'band': b + 1, 'k_first': lo, 'k_last': hi, 'slices': band_n, 'z_mm': [round(dz * lo - dz, 3), round(dz * hi - dz, 3)],
                      'buffer_k': [[lo - buf_n, lo - 1], [hi + 1, hi + buf_n]], 'status_counts': st, 'scoring_slices': int(score_mask.sum()),
                      'paired_fraction': round(float(score_mask.mean()), 3), 'denver_voxels_per_class_on_scoring_slices': per_class,
                      'candidates_at_draw': len(cands)})
    reserved = set()
    for lo_b, hi_b in taken:
        reserved.update(range(lo_b, hi_b + 1))
    training = [k for k in ks if k not in reserved]
    tr_status = {}
    for k in training:
        tr_status[status[k]] = tr_status.get(status[k], 0) + 1
    # supervision density per 50 mm bin from the tissue-classes report
    rep = json.loads(Path(a.classes_report).read_text())
    ign = {r['k']: r['ignore_fraction_of_body'] for r in rep['per_slice'] if 'ignore_fraction_of_body' in r}
    bins = []
    for lo in range(k_first, k_last + 1, band_n):
        hi = min(lo + band_n - 1, k_last)
        vals = [ign[k] for k in range(lo, hi + 1) if k in ign]
        med = float(np.median(vals)) if vals else None
        bins.append({'k': [lo, hi], 'paired_slices': len(vals), 'ignore_fraction_of_body_median': round(med, 4) if med is not None else None,
                     'sparsely_supervised': bool(med is not None and med > a.sparse_ignore)})
    sparse_k = set()
    for b in bins:
        if b['sparsely_supervised']:
            sparse_k.update(range(b['k'][0], b['k'][1] + 1))
    primary = [k for k in training if status[k] in PAIRED and k not in sparse_k]
    auxiliary = [k for k in training if status[k] in PAIRED and k in sparse_k]
    never = [k for k in training if status[k] not in PAIRED]
    low_end = [k for k in range(k_first, k_first + 151) if status[k] in PAIRED]
    doc = {
        'id': 'cryo-eval-bands', 'version': 1, 'date': '2026-09-13', 'block': man['block'],
        'rules': {'band_mm': a.band_mm, 'band_slices': band_n, 'buffer_mm': a.buffer_mm, 'buffer_slices': buf_n, 'bands': a.bands, 'seed': a.seed, 'rng': 'numpy default_rng, uniform choice among remaining candidates, one band at a time',
                  'candidate_starts': '1 mm grid (every %d slices) from k_first' % step, 'candidates_total': len(all_starts),
                  'content_rule': 'at least %.2f of the band slices have pair status usable or usable-flagged' % a.min_paired_fraction,
                  'spacing_rule': 'band plus buffers inside the block; bands with buffers do not overlap',
                  'use': 'bands: evaluation only, scored against Denver original labels through the tissue map on usable and usable-flagged slices; buffers: nothing; the rest: training and pseudo-labelling',
                  'no_human_reference': 'plan B 2.4 revised 13 September 2026: the machine prepares the evaluation from Denver labels; nobody draws a reference; unlabelled regions get consistency reports, not accuracy'},
        'draws': draws, 'rejection': 'candidates failing a rule are filtered before each draw; candidates_at_draw per band says how many remained',
        'bands': bands,
        'training_k_ranges': ranges(training), 'training_slices': len(training), 'training_status_counts': tr_status,
        'reserved_slices_including_buffers': len(reserved),
        'training_eligibility': {
            'rule': 'primary = paired complement slices in densely supervised 50 mm bins; auxiliary = paired complement slices in sparsely supervised bins (median ignore fraction of the body > %.2f, Denver labels only the psoas there); excluded slices are never sampled; a label-density rule, not an anatomical boundary' % a.sparse_ignore,
            'classes_report': str(Path(a.classes_report).relative_to(ROOT)), 'classes_report_sha256': sha256_file(a.classes_report),
            'bins_50mm': bins,
            'primary_k_ranges': ranges(primary), 'primary_slices': len(primary), 'primary_status_counts': {s: sum(1 for k in primary if status[k] == s) for s in PAIRED},
            'auxiliary_k_ranges': ranges(auxiliary), 'auxiliary_slices': len(auxiliary), 'auxiliary_status_counts': {s: sum(1 for k in auxiliary if status[k] == s) for s in PAIRED},
            'auxiliary_use': 'off by default; using it is a separate recorded decision and a new split hash',
            'never_sampled_slices': len(never),
            'lowest_50mm_paired_slices_k': low_end,
            'note_lowest_50mm': 'k 2285..2435 is almost entirely excluded-identity; the %d paired slices there are listed and stay eligible' % len(low_end)},
        'frozen_to': {'manifest': str(Path(a.manifest).relative_to(ROOT)), 'manifest_sha256': sha256_file(a.manifest), 'rgb_sha256': man['outputs']['rgb_sha256'], 'labels_nifti_sha256': man['outputs']['labels_sha256'],
                      'transform_sha256': man['sources']['transform_sha256'], 'pairs_sha256': man['sources']['pairs_sha256'], 'pairs_policy': man['sources']['pairs_policy'],
                      'tissue_map': str(Path(a.tissue_map).relative_to(ROOT)), 'tissue_map_sha256': sha256_file(a.tissue_map), 'tissue_map_version': tmap['version'],
                      'labels_npz_sha256': sha256_file(a.labels), 'labels_mat_sha256': lmeta['source_sha256']},
        'statement': 'frozen before any training; a training set built from a manifest with another hash, or a band edited after this date, invalidates every result scored on it; nothing here is anatomy',
    }
    Path(a.out).write_text(json.dumps(doc, indent=1))
    print(json.dumps({'done': True, 'out': str(Path(a.out).relative_to(ROOT)), 'bands': [(b['k_first'], b['k_last'], b['scoring_slices'], b['denver_voxels_per_class_on_scoring_slices']) for b in bands],
                      'training_slices': len(training), 'primary': len(primary), 'auxiliary': len(auxiliary), 'sha256': sha256_file(a.out)}))


if __name__ == '__main__':
    main()
