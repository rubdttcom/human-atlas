"""Build transforms/nlm-cryosection-to-vhf.json from the alignment check of the colour photographs against Denver.

Input: generated/cryosection-alignment-check.json (scripts/check-cryosection-alignment.py, dense run on rub-pc).
Output: transforms/nlm-cryosection-to-vhf.json: how an NLM colour photograph pixel (column c, row r) of photograph n
maps into the canonical frame VHF-image-2022 (the Denver label-map frame in mm), through Denver's aligned slice grid.

    (u, v) = R(-theta) ((c, r) - (tc, tr)) / s ;  i = -u ;  j = v          (per Denver slice k; the -u is the mirror)
    x = 0.666 i + 316.35 ;  y = 0.666 j + 311.022 ;  z = 0.333 (k - 1) ;  k = offset - n   (VHF_Full.mat ijkToLps)

Regions: consecutive Denver slices with the same photograph offset and the same in-plane similarity (within 2 NLM px
and 0.3 deg) form a region; Denver registered the block in pieces, and each piece has one transform. Inside Denver's
range the per-slice table is the transform. Outside it (NLM photographs above the pelvis, n below the smallest
matched index) no aligned photograph exists: the file carries the pelvis region's transform as an *extrapolation*,
marked unverified, for stage 1 to place priors provisionally; the photograph-to-CT check of stage 0 has to measure it.
Per-slice identity keeps its status: `settled` (label card and frame agree), `frame-with-margin`, or `provisional-block-consistent`
(no card in the crop and a whole-frame margin below 0.005: the block offset is consistency, not identification). Consumers
must read `per_slice[].provisional`. The builder refuses partial or unresolved reports (`check_coverage`). Nothing here is anatomy.
"""
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'generated/cryosection-alignment-check.json'
OUT = ROOT / 'transforms/nlm-cryosection-to-vhf.json'
DENVER_IJK_TO_MM = {'x_mm': [0.666, 316.35], 'y_mm': [0.666, 311.022], 'z_mm': [0.333, -0.333],
                    'note': 'x = 0.666 i + 316.35, y = 0.666 j + 311.022, z = 0.333 k - 0.333 (VHF_Full.mat ijkToLpsTransform, stored transposed)'}
BREAK_PX, BREAK_DEG, MIN_RUN = 2.0, 0.3, 5


def nlm_name(n):
    return f'avf{1001 + n // 3:04d}{"abc"[n % 3]}'


DEN_N = 3533
FRAME_ONLY_MARGIN = 0.005      # below this whole-frame margin a frame-only identity is provisional


def check_coverage(rep):
    """Refuse anything but a complete, unique, resolved dense report: every Denver slice 0..3532 exactly once, every
    non-blank slice matched with a consistent n/offset, no photograph chosen twice. Partial runs (--ks, a truncated
    --refine-from input) carry step == 1 too, so step alone proves nothing."""
    problems = []
    if rep['summary'].get('step') != 1:
        problems.append('step != 1 (%r)' % rep['summary'].get('step'))
    ks = [r['k'] for r in rep['slices']]
    if sorted(ks) != list(range(DEN_N)):
        missing = sorted(set(range(DEN_N)) - set(ks)); dup = sorted({k for k in ks if ks.count(k) > 1})
        problems.append('Denver slices not covered exactly once: %d missing (first %s), %d duplicated (first %s), %d outside 0..%d'
                        % (len(missing), missing[:5], len(dup), dup[:5], sum(1 for k in ks if not 0 <= k < DEN_N), DEN_N - 1))
    counts = {}
    for r in rep['slices']:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    summ = rep['summary']
    if summ.get('statuses') != counts or summ.get('matched') != counts.get('matched', 0) or summ.get('denver_slices_sampled') != len(rep['slices']):
        problems.append('summary counts disagree with the rows: summary %s / matched %r / sampled %r, rows %s / %d'
                        % (summ.get('statuses'), summ.get('matched'), summ.get('denver_slices_sampled'), counts, len(rep['slices'])))
    bad_status = {r['status'] for r in rep['slices']} - {'matched', 'denver-blank'}
    if bad_status:
        problems.append('unresolved slice statuses exported as nothing: %s' % sorted(bad_status))
    seen = {}
    for r in rep['slices']:
        if r['status'] != 'matched':
            continue
        if r.get('n_best') is None or r.get('offset_best') != r['n_best'] + r['k']:
            problems.append('slice k=%d: n_best/offset_best inconsistent' % r['k'])
        if r.get('similarity') is None or (r.get('local_residual') or {}).get('mean_nlm_px') is None:
            problems.append('slice k=%d: matched without similarity or residual' % r['k'])
        seen.setdefault(r['n_best'], []).append(r['k'])
    dups = {n: k for n, k in seen.items() if len(k) > 1}
    if dups:
        problems.append('photographs chosen by several Denver slices: %s' % dict(list(dups.items())[:5]))
    return problems


def identity_of(r, region_offset):
    """Per-slice identity record: how the photograph was chosen and whether that choice is provisional."""
    lab = r.get('label_choice') or {}
    frame = r.get('frame_choice') or {}
    rec = {'identity_by': r['identity_by'], 'label_margin': lab.get('margin'), 'frame_margin': frame.get('margin'),
           'label_and_frame_agree': r.get('label_and_frame_agree'), 'offset_equals_block': r['offset_best'] == region_offset}
    if r['identity_by'] == 'label' and r.get('label_and_frame_agree') is True:
        rec['identity_status'] = 'settled'; rec['resolution'] = 'label card and whole frame chose the same photograph'
    elif r['identity_by'] == 'frame' and (frame.get('margin') or 0) >= FRAME_ONLY_MARGIN and rec['offset_equals_block']:
        rec['identity_status'] = 'frame-with-margin'; rec['resolution'] = 'no label card in the Denver crop; whole-frame margin >= %.3f and offset equal to the block' % FRAME_ONLY_MARGIN
    elif r['identity_by'] == 'frame' and rec['offset_equals_block']:
        rec['identity_status'] = 'provisional-block-consistent'
        rec['resolution'] = ('no label card in the Denver crop and whole-frame margin below %.3f: neighbouring photographs 1/3 mm apart differ '
                             'little in tissue, so the frame alone does not settle the photograph; the choice equals the block offset, which is '
                             'consistency, not identification. Treat as provisional; exclude or flag when pairing RGB with labels.' % FRAME_ONLY_MARGIN)
    else:
        rec['identity_status'] = 'unresolved'; rec['resolution'] = 'identity criteria disagree or the offset differs from the block'
    rec['provisional'] = rec['identity_status'] in ('provisional-block-consistent', 'unresolved')
    if rec['provisional'] or rec['identity_status'] == 'frame-with-margin':
        # the ambiguity set: every present photograph whose whole-frame NCC lies within the margin threshold of the chosen one
        best = frame.get('ncc')
        alts = sorted(c['n'] for c in r.get('candidates', []) if c.get('status') == 'present' and c['n'] != r['n_best']
                      and best is not None and best - c['ncc_frame'] < FRAME_ONLY_MARGIN)
        rec['ambiguity_set_n'] = sorted(alts + [r['n_best']])
        rec['ambiguity_set_nlm'] = [nlm_name(n) for n in rec['ambiguity_set_n']]
        rec['ambiguity_span_mm'] = round((max(rec['ambiguity_set_n']) - min(rec['ambiguity_set_n'])) / 3, 3)
    return rec


def build(rep):
    problems = check_coverage(rep)
    if problems:
        raise SystemExit('report not fit for a transform:\n  ' + '\n  '.join(problems))
    rows = sorted([r for r in rep['slices'] if r['status'] == 'matched'], key=lambda r: r['k'])
    blanks = sorted(r['k'] for r in rep['slices'] if r['status'] == 'denver-blank')
    # regions by breakpoints between consecutive matched slices
    regions = []
    for r in rows:
        s = r['similarity']
        p = (s['tc_nlm_px'], s['tr_nlm_px'], s['rotation_deg'])
        if regions:
            last = regions[-1]; q = last['rows'][-1]['similarity']
            same = (r['offset_best'] == last['offset'] and abs(p[0] - q['tc_nlm_px']) <= BREAK_PX
                    and abs(p[1] - q['tr_nlm_px']) <= BREAK_PX and abs(p[2] - q['rotation_deg']) <= BREAK_DEG
                    and r['k'] - last['rows'][-1]['k'] <= 1 + 20)      # Denver blank bands do not break a region by themselves
            if same:
                last['rows'].append(r); continue
        regions.append({'offset': r['offset_best'], 'rows': [r]})
    # tiny runs are kept but flagged irregular
    out_regions = []
    for idx, g in enumerate(regions):
        rs = g['rows']
        sims = np.array([[x['similarity']['tc_nlm_px'], x['similarity']['tr_nlm_px'], x['similarity']['scale_nlm_px_per_denver_px'], x['similarity']['rotation_deg']] for x in rs])
        med = np.median(sims, axis=0)
        dev = np.abs(sims - med)
        loc = np.array([x['local_residual']['mean_nlm_px'] for x in rs if x['local_residual']['mean_nlm_px'] is not None])
        out_regions.append({
            'region': idx, 'k_first': rs[0]['k'], 'k_last': rs[-1]['k'], 'slices': len(rs), 'irregular': len(rs) < MIN_RUN,
            'z_mm': [round(0.333 * (rs[0]['k'] - 1), 3), round(0.333 * (rs[-1]['k'] - 1), 3)],
            'offset': g['offset'], 'n_first': rs[-1]['n_best'], 'n_last': rs[0]['n_best'],
            'nlm_first': nlm_name(rs[-1]['n_best']), 'nlm_last': nlm_name(rs[0]['n_best']),
            'similarity_median': {'tc_nlm_px': round(float(med[0]), 3), 'tr_nlm_px': round(float(med[1]), 3),
                                  'scale_nlm_px_per_denver_px': round(float(med[2]), 5), 'rotation_deg': round(float(med[3]), 4)},
            'within_region_p95_abs_dev': {'tc_nlm_px': round(float(np.percentile(dev[:, 0], 95)), 3), 'tr_nlm_px': round(float(np.percentile(dev[:, 1], 95)), 3),
                                          'scale': round(float(np.percentile(dev[:, 2], 95)), 5), 'rotation_deg': round(float(np.percentile(dev[:, 3], 95)), 4)},
            'local_residual_mean_nlm_px': {'median': round(float(np.median(loc)), 3), 'p95': round(float(np.percentile(loc, 95)), 3), 'max': round(float(loc.max()), 3)} if len(loc) else None,
            'ncc_full_median': round(float(np.median([x['similarity']['ncc_full'] for x in rs])), 4),
        })
    region_of_k = {}
    for g, grp in zip(out_regions, regions):
        for r in grp['rows']:
            region_of_k[r['k']] = g
    per_slice = []
    for r in rows:
        g = region_of_k[r['k']]
        per_slice.append({'k': r['k'], 'region': g['region'], 'n': r['n_best'], 'nlm': nlm_name(r['n_best']), 'tc': r['similarity']['tc_nlm_px'], 'tr': r['similarity']['tr_nlm_px'],
                          's': r['similarity']['scale_nlm_px_per_denver_px'], 'theta_deg': r['similarity']['rotation_deg'],
                          'residual_mean_nlm_px': r['local_residual']['mean_nlm_px'], 'ncc': r['similarity']['ncc_full'],
                          **identity_of(r, g['offset'])})
    status_counts = {}
    for p in per_slice:
        status_counts[p['identity_status']] = status_counts.get(p['identity_status'], 0) + 1
    for g in out_regions:
        ps = [p for p in per_slice if p['region'] == g['region']]
        g['identity_status_counts'] = {s: sum(1 for p in ps if p['identity_status'] == s) for s in sorted({p['identity_status'] for p in ps})}
        g['provisional_slices_k'] = [p['k'] for p in ps if p['provisional']]
    pelvis = max(out_regions, key=lambda g: g['k_last'])
    n_min = min(r['n_best'] for r in rows)
    fit = rep['summary']['slice_identity_fit']
    doc = {
        'id': 'nlm-cryosection-to-vhf',
        'type': 'per-slice similarity (NLM colour photograph pixel -> Denver aligned slice pixel) composed with the Denver label-map ijk -> mm transform',
        'from': 'NLM Visible Human Female colour photograph avfNNNN{a,b,c}: column c (0..2047), row r (0..1215), index n = 3 (NNNN - 1001) + {a: 0, b: 1, c: 2}',
        'to': 'VHF-image-2022 canonical frame (Denver label-map frame, mm; +x subject right, +z superior; +y = increasing Denver row j, the side of the patella relative to the femur in the Denver label map)',
        'canonical_space': 'VHF-image-2022',
        'formula': {
            'denver_slice_for_photograph': 'k = offset - n (offset per region below)',
            'photograph_to_denver_pixel': '(u, v) = R(-theta) . ((c, r) - (tc, tr)) / s ; i = -u ; j = v  (R(theta) = [[cos, -sin], [sin, cos]]; the -u mirrors left-right)',
            'denver_pixel_to_mm': DENVER_IJK_TO_MM,
            'photograph_axes_measured': 'c increases towards the subject\'s left (Denver +i = subject right, mirrored); r increases towards anterior (the patella lies at larger j than the femur in the Denver label map); n increases towards the feet',
        },
        'regions': out_regions,
        'identity': {'status_counts': status_counts, 'provisional_slices': sum(1 for p in per_slice if p['provisional']),
                     'block_consistency_resolves_nothing': True,
                     'pair_selection': 'scripts/select-cryosection-pairs.py applies the declared policy (pairs-v1) and writes generated/cryosection-pair-selection.json: settled -> usable, frame-with-margin -> usable-flagged, provisional/unresolved -> excluded with their ambiguity sets; blank Denver slices have no reference',
                     'rule': 'settled = label card and whole frame agree; frame-with-margin = no card, frame margin >= %.3f and block offset; provisional-block-consistent = no card and frame margin below that: the block offset is consistency, not identification, so the in-plane residual (which is below 0.1 px everywhere) does not settle which of two neighbouring photographs 1/3 mm apart it is. Consumers pairing RGB with Denver labels must read per_slice[].provisional and exclude or flag those slices; no automatic selection here.' % FRAME_ONLY_MARGIN},
        'denver_blank_slices': blanks,
        'nlm_photographs_in_range_no_denver_slice_chose': rep['summary'].get('nlm_photographs_in_range_no_denver_slice_chose'),
        'nlm_photographs_chosen_by_several_denver_slices': rep['summary'].get('nlm_photographs_chosen_by_several_denver_slices'),
        'extrapolation_above_denver_range': {
            'applies_to': f'photographs with n < {n_min} ({nlm_name(n_min)}), head to pelvis',
            'rule': 'use the pelvis region transform (region %d: offset %d, similarity median) with z = 0.333 (offset - n - 1)' % (pelvis['region'], pelvis['offset']),
            'region': pelvis['region'],
            'status': 'extrapolated-unverified',
            'note': 'Denver publishes no aligned photograph above the pelvis. Whether the photographs keep one frame there is unmeasured until the photograph-to-CT check (plan B stage 0, Denver aligned CT bone and skin contours); Denver itself shifted the lower blocks by up to 1 mm in z and 2 mm in plane and rotated the leg block by about 1.56 deg, so per-block shifts above the pelvis are possible and unknown.',
        },
        'evidence': {'report': str(REPORT.relative_to(ROOT)), 'report_sha256': hashlib.sha256(REPORT.read_bytes()).hexdigest(),
                     'matched_slices': len(rows), 'slice_identity_fit': fit,
                     'criterion': rep['summary']['criterion'], 'local_residual_nlm_px': rep['summary']['local_residual_nlm_px'],
                     'gray_fit': rep['summary']['gray_fit'], 'date': date.today().isoformat()},
        'review_status': 'image-to-image measurement between two publications of the same block; no anatomical review; the extrapolation above the pelvis is unverified',
        'per_slice': per_slice,
    }
    return doc


def main():
    doc = build(json.loads(REPORT.read_text()))
    OUT.write_text(json.dumps(doc, indent=1))
    print(json.dumps({'done': True, 'out': str(OUT.relative_to(ROOT)), 'regions': [(g['region'], g['k_first'], g['k_last'], g['offset'], g['similarity_median'], g['irregular']) for g in doc['regions']],
                      'blank': len(doc['denver_blank_slices']), 'per_slice': len(doc['per_slice']), 'identity': doc['identity']['status_counts']}, indent=None))


if __name__ == '__main__':
    main()
