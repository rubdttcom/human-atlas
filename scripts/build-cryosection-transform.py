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
Nothing here is anatomy.
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


def main():
    rep = json.loads(REPORT.read_text())
    rows = sorted([r for r in rep['slices'] if r['status'] == 'matched'], key=lambda r: r['k'])
    blanks = sorted(r['k'] for r in rep['slices'] if r['status'] == 'denver-blank')
    if rep['summary'].get('step') != 1:
        raise SystemExit('the transform needs the dense run (step 1); got step %r' % rep['summary'].get('step'))
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
    per_slice = [{'k': r['k'], 'n': r['n_best'], 'nlm': nlm_name(r['n_best']), 'tc': r['similarity']['tc_nlm_px'], 'tr': r['similarity']['tr_nlm_px'],
                  's': r['similarity']['scale_nlm_px_per_denver_px'], 'theta_deg': r['similarity']['rotation_deg'],
                  'residual_mean_nlm_px': r['local_residual']['mean_nlm_px'], 'ncc': r['similarity']['ncc_full'],
                  'identity_by': r['identity_by'], 'label_margin': (r['label_choice'] or {}).get('margin')} for r in rows]
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
    OUT.write_text(json.dumps(doc, indent=1))
    print(json.dumps({'done': True, 'out': str(OUT.relative_to(ROOT)), 'regions': [(g['region'], g['k_first'], g['k_last'], g['offset'], g['similarity_median'], g['irregular']) for g in out_regions],
                      'blank': len(blanks), 'per_slice': len(per_slice)}, indent=None))


if __name__ == '__main__':
    main()
