"""End-to-end regression tests of scripts/ct-vertebra-instances.py on small synthetic volumes.

Usage: python scripts/test-ct-instances.py            (about one minute; exits non-zero on any failure)

Every scenario builds three label volumes (TotalSegmentator, MOOSE, Skellytour ids as in the real data), a
CT, a Skellytour plan and merge manifest, runs the real script with --inputs/--out/--no-panels/--no-hra and
checks the JSON and NIfTI outputs. The scenarios cover the decisions the self-test inside the script does
not: candidate extraction, grouping, partition and seed merging, geometric fragment handling, eligibility
from the manifest, per-voxel votes, true unions with conflicts, and invariance to label names across the
whole pipeline.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/ct-vertebra-instances.py'
PY = sys.executable
SHAPE = (96, 64, 220)
SPACING = (0.7, 0.7, 1.0)
AFFINE = np.diag([SPACING[0], SPACING[1], SPACING[2], 1.0])
AFFINE[:3, 3] = [-20, -20, -100]
TS_CLASS = {v: int(k) for k, v in json.loads((ROOT / 'data/derived/nlm-vhf/totalseg-classmap.json').read_text())['total'].items()}
# six bodies, cranial (high z) to caudal, with the names the models would give a normal spine
TS_NAMES = ['vertebrae_T12', 'vertebrae_L1', 'vertebrae_L2', 'vertebrae_L3', 'vertebrae_L4', 'vertebrae_L5']
MO_NAMES = ['vertebra_T12', 'vertebra_L1', 'vertebra_L2', 'vertebra_L3', 'vertebra_L4', 'vertebra_L5']
MO_IDS = {n: i for i, n in enumerate(MO_NAMES, start=19)}
SK_IDS = [35 + 19 + i for i in range(6)]          # VERT_19 .. VERT_24
BODY = 24                                         # voxels in-plane (16.8 mm) and mm tall
GAP = 6
Z_TOP = [190 - i * (BODY + GAP) for i in range(6)]   # z start of each body's cuboid (high z = cranial)
XY = slice(20, 20 + BODY)


def body_mask(i, z0=None, z1=None, xy=XY):
    m = np.zeros(SHAPE, bool)
    a = Z_TOP[i] if z0 is None else z0
    b = Z_TOP[i] + BODY if z1 is None else z1
    m[xy, xy, a:b] = True
    return m


def base():
    ts = np.zeros(SHAPE, np.uint8)
    mo = np.zeros(SHAPE, np.uint8)
    sk = np.zeros(SHAPE, np.uint8)
    for i in range(6):
        m = body_mask(i)
        ts[m] = TS_CLASS[TS_NAMES[i]]
        mo[m] = MO_IDS[MO_NAMES[i]]
        sk[m] = SK_IDS[i]
    return ts, mo, sk


def write_case(d, ts, mo, sk, missing_chunks=(), extra_names=None):
    d.mkdir(parents=True, exist_ok=True)
    hu = np.where((ts > 0) | (mo > 0) | (sk > 0), 400, -50).astype(np.int16)
    for name, arr in [('ts.nii.gz', ts), ('moose.nii.gz', mo), ('hu.nii.gz', hu)]:
        nib.save(nib.Nifti1Image(arr, AFFINE), d / name)
    names = dict(MO_IDS)
    names['sacrum'] = 28
    if extra_names:
        names.update(extra_names)
    (d / 'moose_indices.json').write_text(json.dumps({'organ_indices': {str(i): {'name': n} for n, i in names.items()}}))
    skd = d / 'skellytour'
    skd.mkdir(exist_ok=True)
    chunks = [{'chunk': 0, 'z0': 0, 'z1': 117, 'core0': 0, 'core1': 97}, {'chunk': 1, 'z0': 77, 'z1': 220, 'core0': 97, 'core1': 220}]   # seam at z 97 lies in the gap between bodies 4 and 5
    (skd / 'plan.json').write_text(json.dumps({'crop': [0, 96, 0, 64], 'chunks': chunks}))
    sk = sk.copy()
    for c in missing_chunks:
        sk[:, :, chunks[c]['core0']:chunks[c]['core1']] = 0
    nib.save(nib.Nifti1Image(sk, AFFINE), skd / 'skellytour_high.nii.gz')
    done = [c for c in chunks if c['chunk'] not in missing_chunks]
    (skd / 'skellytour_high.json').write_text(json.dumps({'complete': not missing_chunks, 'missing': list(missing_chunks), 'chunks_planned': len(chunks),
                                                          'chunks': [{'chunk': c['chunk'], 'core0': c['core0'], 'core1': c['core1']} for c in done],
                                                          'crop_ijk': {'i': [0, 96], 'j': [0, 64]}, 'merged_sha256': 'test'}))


def run(d, *flags, expect_fail=False):
    out = d / 'out'
    r = subprocess.run([PY, str(SCRIPT), 'test', 'vertebrae', f'--inputs={d}', f'--out={out}', '--no-panels', '--no-hra', *flags], capture_output=True, text=True)
    if expect_fail:
        return r
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit(f'script failed in {d}')
    js = json.loads((out / 'vertebrae.json').read_text())
    cons = np.asanyarray(nib.load(out / 'nii/vertebrae-instances.nii.gz').dataobj)
    return js, cons


def by_z(js):
    return sorted([i for i in js['instances'] if i['role'] == 'vertebra'], key=lambda i: -i['z_ras_mm'])


results = {}


def check(name, cond, detail=''):
    results[name] = bool(cond)
    print(('PASS' if cond else 'FAIL'), name, detail, flush=True)


tmp = Path(tempfile.mkdtemp(prefix='ct-instances-test-'))
try:
    # T1 baseline
    ts, mo, sk = base()
    d = tmp / 't1'
    write_case(d, ts, mo, sk)
    js1, cons1 = run(d)
    v = by_z(js1)
    check('T1 six full consensus instances', js1['instance_count']['vertebra_consensus_full'] == 6 and js1['instance_count']['vertebra_pieces'] == 0, js1['instance_count'])
    check('T1 all matched, unanimous, no conflicts', all(all(m['state'] == 'matched' for m in i['models'].values()) and i['unanimous_fraction'] == 1.0 for i in v) and js1['instance_count']['conflict_voxels'] == 0)
    check('T1 consensus volume equals the drawn bodies', abs(sum(i['consensus_ml'] for i in v) - 6 * BODY * BODY * BODY * 0.7 * 0.7 / 1000) < 0.05)

    # T2 label names permuted in every model: identical geometry -> identical instances and consensus map
    ts, mo, sk = base()
    perm = [3, 5, 0, 2, 4, 1]
    ts2, mo2, sk2 = np.zeros_like(ts), np.zeros_like(mo), np.zeros_like(sk)
    for i in range(6):
        m = body_mask(i)
        ts2[m] = TS_CLASS[TS_NAMES[perm[i]]]
        mo2[m] = MO_IDS[MO_NAMES[perm[i]]]
        sk2[m] = SK_IDS[perm[i]]
    d = tmp / 't2'
    write_case(d, ts2, mo2, sk2)
    js2, cons2 = run(d)
    strip = lambda js: [{k: v for k, v in i.items() if k not in ('source_labels', 'models', 'hra_name_by_order', 'hra_z_offset_mm')} for i in js['instances']]  # noqa: E731
    check('T2 renamed labels: consensus map identical', np.array_equal(cons1, cons2))
    check('T2 renamed labels: instance table identical (geometry fields)', strip(js1) == strip(js2))

    # T3 MOOSE merges bodies 3 and 4 into one label (bridging the gap)
    ts, mo, sk = base()
    mo[body_mask(3, z1=Z_TOP[2] + BODY)] = MO_IDS[MO_NAMES[2]]
    d = tmp / 't3'
    write_case(d, ts, mo, sk)
    js3, cons3 = run(d)
    v = by_z(js3)
    check('T3 merged MOOSE label: still six full instances', js3['instance_count']['vertebra_consensus_full'] == 6)
    check('T3 MOOSE state merge on both bodies, others matched', v[2]['models']['moose']['state'] == 'merge' and v[3]['models']['moose']['state'] == 'merge' and v[2]['models']['totalseg']['state'] in ('seed', 'matched'))
    check('T3 consensus map unchanged by the merge', np.array_equal(cons1, cons3))

    # T4 TotalSegmentator splits body 2 into two labels (upper half T12, lower half L1): seeds must be re-merged
    ts, mo, sk = base()
    ts[body_mask(1, z0=Z_TOP[1], z1=Z_TOP[1] + BODY // 2)] = TS_CLASS['vertebrae_L2']
    ts[body_mask(1, z0=Z_TOP[1] + BODY // 2)] = TS_CLASS['vertebrae_L1']
    ts[body_mask(2)] = TS_CLASS['vertebrae_L3']
    ts[body_mask(3)] = TS_CLASS['vertebrae_L4']
    ts[body_mask(4)] = TS_CLASS['vertebrae_L5']
    ts[body_mask(5)] = TS_CLASS['vertebrae_S1']
    d = tmp / 't4'
    write_case(d, ts, mo, sk)
    js4, cons4 = run(d)
    v = by_z(js4)
    check('T4 split TS label: six full instances', js4['instance_count']['vertebra_consensus_full'] == 6, js4['instance_count'])
    check('T4 the split body records seed_merged_from', bool(v[1].get('seed_merged_from')) and len(v[1]['seed_merged_from']) == 2, v[1].get('seed_merged_from'))
    check('T4 consensus map unchanged by the split', np.array_equal(cons1, cons4))

    # T5 Skellytour misses body 5: negative vote, 2 of 3
    ts, mo, sk = base()
    sk[body_mask(4)] = 0
    d = tmp / 't5'
    write_case(d, ts, mo, sk)
    js5, cons5 = run(d)
    v = by_z(js5)
    check('T5 missing Skellytour body: negative state, consensus kept by 2 of 3', v[4]['models']['skellytour']['state'] == 'negative' and v[4]['consensus_ml'] > 0 and v[4]['unanimous_fraction'] == 0.0 and v[4]['eligible_models_on_consensus'] == {'3': int(body_mask(4).sum())})

    # T6 missing Skellytour chunk (bodies at z >= 110): unprocessed, eligible 2, unanimity intact; refused without the flag
    ts, mo, sk = base()
    d = tmp / 't6'
    write_case(d, ts, mo, sk, missing_chunks=(1,))
    r = run(d, expect_fail=True)
    check('T6 incomplete manifest refused without --allow-incomplete', r.returncode != 0 and 'incomplete' in (r.stdout + r.stderr))
    js6, cons6 = run(d, '--allow-incomplete')
    v = by_z(js6)
    upper = [i for i in v if i['z_ras_mm'] > AFFINE[2, 3] + 97]
    lower = [i for i in v if i['z_ras_mm'] < AFFINE[2, 3] + 97]
    check('T6 bodies in the missing chunk: skellytour unprocessed, eligible 2, unanimous 1.0',
          upper and all(i['models']['skellytour']['state'] == 'unprocessed' and list(i['eligible_models_on_consensus']) == ['2'] and i['unanimous_fraction'] == 1.0 for i in upper),
          [(i['id'], i['models']['skellytour']['state'], i['eligible_models_on_consensus']) for i in upper])
    check('T6 bodies in the done chunk unchanged', lower and all(i['models']['skellytour']['state'] == 'matched' and list(i['eligible_models_on_consensus']) == ['3'] for i in lower))
    check('T6 consensus map unchanged', np.array_equal(cons1, cons6))

    # T7 detached piece beside the upper half of body 3 in TS and MOOSE (same labels as body 3), 3.1 mL (< 0.5 x body):
    # 2.8 mm away it is merged geometrically; 14 mm away it stays a separate piece
    for tag, x0 in [('near', 48), ('far', 64)]:
        ts, mo, sk = base()
        piece = np.zeros(SHAPE, bool)
        piece[x0:x0 + 22, XY, Z_TOP[2] + 12:Z_TOP[2] + BODY] = True    # 22 x 24 x 12 voxels x 0.49 mm3 = 3.1 mL
        ts[piece] = TS_CLASS[TS_NAMES[2]]
        mo[piece] = MO_IDS[MO_NAMES[2]]
        d = tmp / f't7-{tag}'
        write_case(d, ts, mo, sk)
        js7, cons7 = run(d)
        if tag == 'near':
            frag = [i for i in js7['instances'] if i.get('fragments')]
            check('T7 near piece merged as fragment (geometry), six full instances', js7['instance_count']['vertebra_consensus_full'] == 6 and js7['instance_count']['vertebra_pieces'] == 0 and len(frag) == 1
                  and frag[0]['fragments'][0]['surface_distance_mm'] < 4.0, (js7['instance_count'], frag[0]['fragments'] if frag else None))
        else:
            pieces = [i for i in js7['instances'] if i.get('size_class') == 'piece']
            check('T7 far piece kept separate as size_class piece, six full instances', js7['instance_count']['vertebra_consensus_full'] == 6 and js7['instance_count']['vertebra_pieces'] == 1 and len(pieces) == 1 and not any(i.get('fragments') for i in js7['instances']),
                  js7['instance_count'])

    # T8 conflicting boundaries: TS body 5 grows 4 mm into the gap below, MOOSE body 6 grows 4 mm into the same gap
    ts, mo, sk = base()
    gap_top = Z_TOP[5] + BODY          # gap between body 6 (below, ends at gap_top) and body 5 (above, starts at gap_top + GAP)
    ts[XY, XY, gap_top + 2:gap_top + GAP] = TS_CLASS[TS_NAMES[4]]     # body 5 grows 4 mm down, contiguous with itself
    mo[XY, XY, gap_top:gap_top + 4] = MO_IDS[MO_NAMES[5]]             # body 6 grows 4 mm up; shared slices gap_top+2 .. gap_top+4
    d = tmp / 't8'
    write_case(d, ts, mo, sk)
    js8, cons8 = run(d)
    v = by_z(js8)
    shared = int((BODY * BODY) * 2)     # voxels z gap_top+2..gap_top+4 carry TS -> body 5 and MOOSE -> body 6
    check('T8 conflict voxels counted on both instances', v[4]['conflict_voxels'] == shared and v[5]['conflict_voxels'] == shared, (v[4]['conflict_voxels'], v[5]['conflict_voxels'], shared))
    check('T8 union of the losing instance keeps the contested voxels', v[5]['union_ml'] > v[5]['consensus_ml'] and v[5]['lost_to_other_winner_ml'] > 0 and v[5]['votes_histogram_on_union'].get('1', 0) >= shared, (v[5]['union_ml'], v[5]['consensus_ml'], v[5]['lost_to_other_winner_ml']))
    check('T8 contested voxels are not consensus', np.array_equal(cons1, cons8))
    model_maps = [Path(js8['volumes'][f'model-{m}']) for m in ('totalseg', 'moose', 'skellytour')]
    check('T8 per-model instance maps written', all(p.exists() for p in model_maps), [str(p) for p in model_maps])

    # T9 anisotropic nearest-seed split. MOOSE merges bodies 3 and 4 and bridges the gap. TS body 3 is two voxels narrower
    # in x, TS body 4 reaches two slices into the gap. The gap voxel at (x = 43, z = g0 + 4) is 3 voxels in x from body 3
    # and 2 slices in z, and 3 slices in z from body 4 with no x offset: in voxel units body 4 is nearer (3.0 < 3.6),
    # in millimetres body 3 is nearer (2.9 < 3.0). The correct (mm) assignment is body 3.
    ts, mo, sk = base()
    g0 = Z_TOP[3] + BODY
    ts[body_mask(2)] = 0
    ts[20:41, XY, Z_TOP[2]:Z_TOP[2] + BODY] = TS_CLASS[TS_NAMES[2]]
    ts[XY, XY, g0:g0 + 2] = TS_CLASS[TS_NAMES[3]]
    mo[body_mask(3, z1=Z_TOP[2] + BODY)] = MO_IDS[MO_NAMES[2]]
    d = tmp / 't9'
    write_case(d, ts, mo, sk)
    js9, cons9 = run(d)
    mm = np.asanyarray(nib.load(Path(js9['volumes']['model-moose'])).dataobj)
    v = by_z(js9)
    probe = mm[43, 32, g0 + 4]
    check('T9 nearest-seed split uses millimetres, not voxels', probe == v[2]['index'], (int(probe), v[2]['index'], v[3]['index']))
    # T10 a small body (about 3.3 mL, below half the median) that all three models segment 3 mm from body 6 is a small bone,
    # not a piece: it stays a separate full instance (rib 12 and C3 are this case)
    ts, mo, sk = base()
    small = np.zeros(SHAPE, bool)
    small[XY, XY, Z_TOP[5] - 3 - 14:Z_TOP[5] - 3] = True     # 24 x 24 x 14 x 0.49 mm3 = 3.95 mL... use 12 slices = 3.4 mL
    small[:] = False
    small[XY, XY, Z_TOP[5] - 3 - 11:Z_TOP[5] - 3] = True   # 24 x 24 x 11 x 0.49 mm3 = 3.1 mL, below half of 6.77
    ts[small] = TS_CLASS['vertebrae_S1']
    mo[small] = MO_IDS['vertebra_L5'] + 1          # id 25 = vertebra_L6 in the real MOOSE vocabulary
    sk[small] = 35 + 25 if False else SK_IDS[5] - 1  # reuse VERT_18 (unused by the six bodies) as a seventh Skellytour label
    d = tmp / 't10'
    write_case(d, ts, mo, sk, extra_names={'vertebra_L6': 25})
    js10, cons10 = run(d)
    v = by_z(js10)
    check('T10 small body seen by all models stays a full instance', js10['instance_count']['vertebra_consensus_full'] == 7 and js10['instance_count']['vertebra_pieces'] == 0
          and v[-1].get('small_but_fully_supported') is True and not any(i.get('fragments') for i in js10['instances']), js10['instance_count'])
    # T11 chained pieces A -> B -> body: A is near B only, B is near body 2 only; both TS+MOOSE, absent in Skellytour.
    # Both must end in body 2 with their voxels and provenance, no exception, six full instances.
    ts, mo, sk = base()
    A = np.zeros(SHAPE, bool); B = np.zeros(SHAPE, bool)
    B[48:70, XY, Z_TOP[1] + 12:Z_TOP[1] + BODY] = True          # 3.1 mL, 2.8 mm lateral to body 2's upper half
    A[74:96, XY, Z_TOP[1] + 12:Z_TOP[1] + BODY] = True          # 3.1 mL, 2.8 mm lateral to B, 21 mm from body 2
    for arr, lab in [(ts, TS_CLASS[TS_NAMES[1]]), (mo, MO_IDS[MO_NAMES[1]])]:
        arr[A] = lab
        arr[B] = lab
    d = tmp / 't11'
    write_case(d, ts, mo, sk)
    js11, cons11 = run(d)
    v = by_z(js11)
    body = max(v[:3], key=lambda i: i['union_ml'])      # the pieces sit at the same height as body 2's upper half
    frags = body.get('fragments') or []
    expect_union = round((BODY * BODY * BODY + 2 * 22 * 24 * 12) * 0.49 / 1000, 2)
    check('T11 chained pieces both merged into body 2, voxels and provenance kept', js11['instance_count']['vertebra_consensus_full'] == 6 and js11['instance_count']['vertebra_pieces'] == 0
          and len(frags) == 2 and abs(body['union_ml'] - expect_union) < 0.05 and abs(body['consensus_ml'] - expect_union) < 0.05,
          (js11['instance_count'], len(frags), body['union_ml'], body['consensus_ml'], expect_union))
    check('T11 consensus map contains both pieces under body 2', int((cons11 == body['index']).sum()) == BODY ** 3 + 2 * 22 * 24 * 12, int((cons11 == body['index']).sum()))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

failed = [k for k, ok in results.items() if not ok]
print(f'\n{len(results) - len(failed)} passed, {len(failed)} failed')
if failed:
    sys.exit(1)
