"""Validator of the cryosection pilot registries (plan B stage 2 preparation, roadmap 6b steps 1 to 4).

Checks, with no data volume needed (hashes and JSON only):
  manifest   generated/cryosection-rgb-block2-manifest.json: one row per Denver slice of the block, statuses equal the pair
             selection (region 2 counts and per-slice status), every resampled slice has photograph hashes and an NCC at or
             above the manifest's own threshold, mirror controls all lower, transform and pairs hashes consistent with the
             files in the repository
  map        registry/cryo-tissue-map.json: 131 labels, value = index, every class value declared, Bone/Cartilage/Ligament/
             Muscle names map to their class, precedence text present, version 1
  bands      registry/cryo-eval-bands-v1.json: two bands of 150 slices with 30-slice buffers inside the block, no overlap,
             content rule met, training ranges = block minus bands minus buffers, frozen hashes equal the current manifest,
             map and label slab (if present), per-class voxel counts on scoring slices recomputed from the label slab when it
             is on disk
  protocol   registry/machine-acceptance-protocol-v1.json: fixed_now hashes equal the current files, thresholds equal the
             noise-floor figures (bone H, muscle H - 0.03, P per class, rounded to 4 decimals), min_reference_voxels present,
             every assessed class has a criterion, no "validated"/"confirmed" wording, statuses vocabulary complete
  classes    generated/cryo-tissue-classes-block2.json (when present): sources hashes equal manifest and map, ignored slices
             equal the manifest's non-paired count
Exit 1 on the first failure with the reason. A passing validator is consistency between files, not anatomy.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = {
    'manifest': ROOT / 'generated/cryosection-rgb-block2-manifest.json',
    'pairs': ROOT / 'generated/cryosection-pair-selection.json',
    'transform': ROOT / 'transforms/nlm-cryosection-to-vhf.json',
    'map': ROOT / 'registry/cryo-tissue-map.json',
    'bands': ROOT / 'registry/cryo-eval-bands-v1.json',
    'protocol': ROOT / 'registry/machine-acceptance-protocol-v1.json',
    'floor': ROOT / 'generated/denver-noise-floor.json',
    'classes': ROOT / 'generated/cryo-tissue-classes-block2.json',
    'labels_npz': ROOT / 'data/derived/denver/label-blocks/block2-k2285-3532-labels.npz',
}
PAIRED = ('usable', 'usable-flagged')
FORBIDDEN = re.compile(r'\b(validated|confirmed|anatomically correct)\b', re.I)


def fail(msg):
    print(json.dumps({'ok': False, 'error': msg}))
    sys.exit(1)


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sha_json(doc):
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


def load(name):
    if not P[name].exists():
        fail(f'missing {P[name].relative_to(ROOT)}')
    return json.loads(P[name].read_text())


def check_manifest(man, pairs, transform):
    b = man['block']
    ks = list(range(b['k_first'], b['k_last'] + 1))
    rows = {r['k']: r for r in man['per_slice']}
    if sorted(rows) != ks:
        fail('manifest per_slice does not cover the block exactly once')
    if man['sources']['transform_sha256'] != sha_json(transform):
        fail('manifest transform hash differs from transforms/nlm-cryosection-to-vhf.json')
    if man['sources']['pairs_sha256'] != sha_json(pairs):
        fail('manifest pairs hash differs from generated/cryosection-pair-selection.json')
    exp = {}
    for k in pairs['usable_k']:
        exp[k] = 'usable'
    for e in pairs['usable_flagged']:
        exp[e['k']] = 'usable-flagged'
    for e in pairs['excluded_identity']:
        exp[e['k']] = 'excluded-identity'
    for e in pairs['excluded_observability']:
        exp[e['k']] = 'excluded-observability'
    for k in pairs['no_reference_blank_denver_k']:
        exp[k] = 'no-reference-blank-denver'
    for k in ks:
        if rows[k]['status'] != exp.get(k):
            fail(f'slice {k}: manifest status {rows[k]["status"]} differs from pair selection {exp.get(k)}')
    reg = pairs['per_region'][str(b['region'])]
    if (man['counts'].get('usable', 0), man['counts'].get('usable-flagged', 0), man['counts'].get('excluded-identity', 0), man['counts'].get('excluded-observability', 0)) != \
            (reg['usable'], reg['usable_flagged'], reg['excluded_identity'], reg['excluded_observability']):
        fail('manifest counts differ from the pair selection region counts')
    thr = man['check']['ncc_min_threshold']
    for k in ks:
        r = rows[k]
        if r['status'] in PAIRED:
            for f in ('photo_compressed_sha256', 'photo_raw_sha256', 'denver_sha256', 'ncc_luminance_vs_denver'):
                if r.get(f) is None:
                    fail(f'slice {k}: resampled row without {f}')
            if r['ncc_luminance_vs_denver'] < thr and k not in man['check']['below_threshold_k']:
                fail(f'slice {k}: NCC below threshold and not listed')
            if 'ncc_mirror_control' in r and not r['ncc_mirror_control'] < r['ncc_luminance_vs_denver']:
                fail(f'slice {k}: mirror control not lower')
        elif r['status'] in ('excluded-identity',) and not r.get('ambiguity_set_nlm'):
            fail(f'slice {k}: excluded-identity without ambiguity set')
    if man['check']['mirror_controls'] and man['check']['mirror_control_lower_in_all'] is not True:
        fail('manifest says a mirror control was not lower')
    if man['grid']['shape_kji3'] != [len(ks), 434, 666, 3]:
        fail('manifest grid shape unexpected')
    return ks


def check_map(tmap):
    if tmap['version'] != 1 or tmap['id'] != 'cryo-tissue-map':
        fail('tissue map id/version')
    vals = {c['value'] for c in tmap['classes']}
    if vals != {0, 1, 2, 3, 4, 5, 255}:
        fail('tissue map classes are not 0..5 + 255')
    if len(tmap['labels']) != 131:
        fail('tissue map must list 131 Denver labels')
    want = {'Bone': 1, 'Cartilage': 2, 'Ligament': 4, 'Muscle': 3}
    for i, r in enumerate(tmap['labels']):
        if r['value'] != i:
            fail(f'tissue map label value {r["value"]} is not its index {i}')
        if i == 0:
            if r['class'] != 0:
                fail('Denver 0 must map to background (with the body-mask precedence)')
            continue
        m = re.match(r'^(Left|Right)_(Bone|Cartilage|Ligament|Muscle)_', r['name'])
        if not m or r['class'] != want[m.group(2)]:
            fail(f'tissue map: {r["name"]} -> class {r["class"]} contradicts its Denver tissue')
    if not any('ignore' in p and 'never background' in p for p in tmap['precedence']):
        fail('tissue map precedence must state unknown inside the body = ignore, never background')
    if 'body_mask_rule' not in tmap:
        fail('tissue map without body mask rule')


def check_bands(bands, man, tmap, ks):
    r = bands['rules']
    if bands['version'] != 1 or r['bands'] != 2 or r['band_slices'] != 150 or r['buffer_slices'] != 30:
        fail('band rules differ from the frozen design (2 x 150 slices, 30-slice buffers)')
    if len(bands['bands']) != 2:
        fail('two bands expected')
    status = {row['k']: row['status'] for row in man['per_slice']}
    reserved = set()
    spans = []
    for b in bands['bands']:
        lo, hi = b['k_first'], b['k_last']
        if hi - lo + 1 != 150:
            fail(f'band {b["band"]} is not 150 slices')
        blo, bhi = lo - 30, hi + 30
        if blo < ks[0] or bhi > ks[-1]:
            fail(f'band {b["band"]} with buffers leaves the block')
        if b['buffer_k'] != [[blo, lo - 1], [hi + 1, bhi]]:
            fail(f'band {b["band"]} buffers mis-stated')
        paired = sum(1 for k in range(lo, hi + 1) if status[k] in PAIRED)
        if paired != b['scoring_slices'] or paired / 150 < 0.70:
            fail(f'band {b["band"]} scoring slices {paired} differ from the file or below the content rule')
        spans.append((blo, bhi)); reserved.update(range(blo, bhi + 1))
    (a0, a1), (b0, b1) = sorted(spans)
    if a1 >= b0:
        fail('bands with buffers overlap')
    training = [k for k in ks if k not in reserved]
    flat = [k for lo, hi in bands['training_k_ranges'] for k in range(lo, hi + 1)]
    if flat != training or bands['training_slices'] != len(training):
        fail('training ranges are not the block minus bands minus buffers')
    f = bands['frozen_to']
    if f['manifest_sha256'] != sha_file(P['manifest']):
        fail('bands frozen to another manifest')
    if f['rgb_sha256'] != man['outputs']['rgb_sha256'] or f['labels_nifti_sha256'] != man['outputs']['labels_sha256']:
        fail('bands frozen to other volume hashes')
    if f['tissue_map_sha256'] != sha_file(P['map']):
        fail('bands frozen to another tissue map')
    if P['labels_npz'].exists():
        if f['labels_npz_sha256'] != sha_file(P['labels_npz']):
            fail('bands frozen to another label slab')
        import numpy as np
        z = np.load(P['labels_npz'], allow_pickle=False)
        labels = z['labels']
        cls_of = {row['value']: row['class'] for row in tmap['labels']}
        cls_name = {c['value']: c['name'] for c in tmap['classes']}
        for b in bands['bands']:
            sl = labels[b['k_first'] - ks[0]:b['k_last'] - ks[0] + 1]
            mask = np.array([status[k] in PAIRED for k in range(b['k_first'], b['k_last'] + 1)])
            counts = np.bincount(sl[mask].ravel(), minlength=256)
            per = {}
            for v, c in enumerate(counts):
                if c and v:
                    per[cls_name[cls_of[v]]] = per.get(cls_name[cls_of[v]], 0) + int(c)
            if per != b['denver_voxels_per_class_on_scoring_slices']:
                fail(f'band {b["band"]} per-class voxel counts do not reproduce from the label slab')


def check_protocol(prot, man, bands, floor):
    if prot['version'] != 1:
        fail('protocol version')
    fx = prot['identity_by_hash']['fixed_now']
    if fx['rgb_block_manifest_sha256'] != sha_file(P['manifest']):
        fail('protocol bound to another manifest')
    if fx['rgb_volume_sha256'] != man['outputs']['rgb_sha256']:
        fail('protocol bound to another RGB volume')
    if fx['tissue_map_sha256'] != sha_file(P['map']):
        fail('protocol bound to another tissue map')
    if fx['eval_bands_sha256'] != sha_file(P['bands']):
        fail('protocol bound to other evaluation bands')
    if fx['noise_floor_sha256'] != sha_file(P['floor']) or prot['noise_floor']['sha256'] != sha_file(P['floor']):
        fail('protocol bound to another noise floor')
    pc = floor['per_class']
    H = {c.lower(): round(pc[c]['H_dice_median'], 4) for c in pc}
    Pp = {c.lower(): round(pc[c]['P_p95_mm_median'], 4) for c in pc}
    if prot['noise_floor']['H_dice_median'] != H or prot['noise_floor']['P_p95_mm_median'] != Pp:
        fail('protocol noise-floor figures differ from generated/denver-noise-floor.json')
    cr = prot['criteria']
    if cr['bone']['dice_min'] != H['bone'] or cr['bone']['surface_p95_mm_max'] != Pp['bone']:
        fail('bone criterion is not H_bone / P_bone')
    if cr['muscle']['dice_min'] != round(H['muscle'] - 0.03, 4) or cr['muscle']['surface_p95_mm_max'] != Pp['muscle']:
        fail('muscle criterion is not H_muscle - 0.03 / P_muscle')
    if cr['cartilage']['dice_min'] is not None or cr['cartilage']['surface_p95_mm_max'] != Pp['cartilage']:
        fail('cartilage criterion is not p95 <= P_cartilage only')
    for c in prot['scope']['classes_assessed']:
        if c not in cr or 'min_reference_voxels' not in cr[c]:
            fail(f'assessed class {c} without a criterion or minimum support')
    for c in ('mirror', 'shift', 'dilation', 'wrong_neighbour'):
        if c not in prot['negative_controls'] or 'required' not in prot['negative_controls'][c]:
            fail(f'negative control {c} missing or without a requirement')
    if set(prot['statuses']) < {'machine-accepted', 'machine-failed', 'machine-not-assessable'}:
        fail('status vocabulary incomplete')
    if prot['iteration_limit']['training_runs_per_variant'] < 1:
        fail('iteration limit')
    text = P['protocol'].read_text()
    m = FORBIDDEN.search(text.replace('never called validation', '').replace('never validation', ''))
    if m:
        fail(f'protocol wording: "{m.group(0)}"')
    if 'never anatomical accuracy' not in ' '.join(prot['limits']) and 'never anatomical accuracy, never validation' not in ' '.join(prot['limits']):
        fail('protocol limits must say never anatomical accuracy')
    b = bands['block']
    if str(b['k_first']) not in prot['scope']['region'] or str(b['k_last']) not in prot['scope']['region']:
        fail('protocol region does not name the block slices')


def check_classes(rep, man):
    if rep['sources']['manifest_sha256'] != sha_file(P['manifest']) or rep['sources']['tissue_map_sha256'] != sha_file(P['map']):
        fail('tissue-classes report built from other inputs')
    non_paired = sum(1 for r in man['per_slice'] if r['status'] not in PAIRED)
    if rep['ignored_slices'] != non_paired:
        fail('tissue-classes ignored slices differ from the manifest')
    if rep['voxels_per_class'].get('fat', 0) != 0 or rep['voxels_per_class'].get('ligament-tendon', 0) != 0:
        fail('fat or ligament voxels appeared in block 2 (no source)')


def main():
    man, pairs, transform, tmap, bands, prot, floor = (load(n) for n in ('manifest', 'pairs', 'transform', 'map', 'bands', 'protocol', 'floor'))
    ks = check_manifest(man, pairs, transform)
    check_map(tmap)
    check_bands(bands, man, tmap, ks)
    check_protocol(prot, man, bands, floor)
    classes = P['classes'].exists()
    if classes:
        check_classes(json.loads(P['classes'].read_text()), man)
    print(json.dumps({'ok': True, 'block_slices': len(ks), 'manifest_counts': man['counts'], 'bands': [[b['k_first'], b['k_last'], b['scoring_slices']] for b in bands['bands']],
                      'training_slices': bands['training_slices'], 'protocol_version': prot['version'], 'classes_report_checked': classes,
                      'statement': 'consistency between files; not anatomy'}))


if __name__ == '__main__':
    main()
