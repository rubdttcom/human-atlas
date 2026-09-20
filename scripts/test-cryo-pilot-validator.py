"""Corruption tests of scripts/validate-cryo-pilot.py (Codex audit of 4da4b5b, P2 finding 4): every in-memory mutation below
must make the corresponding check fail, and the unmodified documents must pass. Hash-pointer checks are exercised by the
validator itself; these cases cover the semantic assertions (row = transform, names = source, eligibility, thresholds).

  .venv/bin/python scripts/test-cryo-pilot-validator.py
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vcp', ROOT / 'scripts/validate-cryo-pilot.py')
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)

man = json.loads(V.P['manifest'].read_text())
pairs = json.loads(V.P['pairs'].read_text())
transform = json.loads(V.P['transform'].read_text())
inventory = json.loads(V.P['inventory'].read_text())
tmap = json.loads(V.P['map'].read_text())
bands = json.loads(V.P['bands'].read_text())
prot = json.loads(V.P['protocol'].read_text())
floor = json.loads(V.P['surface_floor'].read_text())
classes = json.loads(V.P['classes'].read_text())
hashes = {n: V.sha_file(V.P[n]) for n in ('manifest', 'map', 'bands', 'floor', 'surface_floor', 'metrics', 'evaluator', 'classes', 'rn_reference')}
results = {}


def expect_fail(name, fn):
    try:
        fn()
    except SystemExit as e:
        results[name] = True
        return
    results[name] = False
    print('DID NOT FAIL', name)


def expect_pass(name, fn):
    try:
        fn(); results[name] = True
    except SystemExit as e:
        results[name] = False; print('UNEXPECTED FAIL', name, e)


ks = list(range(man['block']['k_first'], man['block']['k_last'] + 1))
first_usable = next(r for r in man['per_slice'] if r['status'] == 'usable')
idx = man['per_slice'].index(first_usable)

expect_pass('manifest_ok', lambda: V.check_manifest(man, pairs, transform, inventory))
expect_pass('map_ok', lambda: V.check_map(tmap, man))
expect_pass('bands_ok', lambda: V.check_bands(bands, man, tmap, ks, classes))
expect_pass('protocol_ok', lambda: V.check_protocol(prot, man, bands, floor, hashes))
expect_pass('classes_ok', lambda: V.check_classes(classes, man))


def mut_manifest(field, value):
    m = copy.deepcopy(man); m['per_slice'][idx][field] = value; return m


expect_fail('manifest_wrong_n', lambda: V.check_manifest(mut_manifest('n', first_usable['n'] + 1), pairs, transform, inventory))
expect_fail('manifest_wrong_tc', lambda: V.check_manifest(mut_manifest('tc', first_usable['tc'] + 100), pairs, transform, inventory))
expect_fail('manifest_wrong_theta', lambda: V.check_manifest(mut_manifest('theta_deg', first_usable['theta_deg'] + 0.5), pairs, transform, inventory))
expect_fail('manifest_wrong_identity_status', lambda: V.check_manifest(mut_manifest('identity_status', 'frame-with-margin'), pairs, transform, inventory))
expect_fail('manifest_wrong_photo_hash', lambda: V.check_manifest(mut_manifest('photo_compressed_sha256', '0' * 64), pairs, transform, inventory))
expect_fail('manifest_wrong_nlm', lambda: V.check_manifest(mut_manifest('nlm', 'avf1001a.raw.Z'), pairs, transform, inventory))
expect_fail('manifest_status_swapped', lambda: V.check_manifest(mut_manifest('status', 'usable-flagged'), pairs, transform, inventory))


def m2():
    m = copy.deepcopy(man); m['per_slice'][idx]['ncc_luminance_vs_denver'] = 0.5; return m


expect_fail('manifest_low_ncc_unlisted', lambda: V.check_manifest(m2(), pairs, transform, inventory))


def map_invented_name():
    t = copy.deepcopy(tmap); t['labels'][4]['name'] = 'Left_Bone_Invented'; return t


def map_wrong_class():
    t = copy.deepcopy(tmap); t['labels'][4]['class'] = 3; t['labels'][4]['class_name'] = 'muscle'; return t


def man_wrong_source_names():
    m = copy.deepcopy(man); m['outputs']['label_names'][4] = 'Left_Bone_Invented'; return m


expect_fail('map_invented_name', lambda: V.check_map(map_invented_name(), man))
expect_fail('map_wrong_class', lambda: V.check_map(map_wrong_class(), man))
expect_fail('map_source_names_differ_from_npz', lambda: V.check_map(tmap, man_wrong_source_names(), man['outputs']['label_names']))
expect_fail('map_vs_npz_names', lambda: V.check_map(tmap, man, ['x'] * 131))


def bands_shifted():
    b = copy.deepcopy(bands); b['bands'][0]['k_first'] += 1; b['bands'][0]['k_last'] += 1; b['bands'][0]['buffer_k'] = [[b['bands'][0]['k_first'] - 30, b['bands'][0]['k_first'] - 1], [b['bands'][0]['k_last'] + 1, b['bands'][0]['k_last'] + 30]]; return b


def bands_primary_padded():
    b = copy.deepcopy(bands); b['training_eligibility']['primary_slices'] += 1; return b


def bands_bin_flipped():
    b = copy.deepcopy(bands); b['training_eligibility']['bins_50mm'][-1]['sparsely_supervised'] = False; return b


def bands_training_leak():
    b = copy.deepcopy(bands); b['training_k_ranges'][0][1] += 1; return b


expect_fail('bands_shifted', lambda: V.check_bands(bands_shifted(), man, tmap, ks, classes))
expect_fail('bands_primary_count', lambda: V.check_bands(bands_primary_padded(), man, tmap, ks, classes))
expect_fail('bands_bin_flipped', lambda: V.check_bands(bands_bin_flipped(), man, tmap, ks, classes))
expect_fail('bands_training_leak_into_buffer', lambda: V.check_bands(bands_training_leak(), man, tmap, ks, classes))


def prot_threshold():
    p = copy.deepcopy(prot); p['criteria']['bone']['dice_min'] -= 0.01; return p


def prot_muscle_offset():
    p = copy.deepcopy(prot); p['criteria']['muscle']['dice_min'] = round(p['criteria']['muscle']['dice_min'] - 0.02, 4); return p


def prot_missing_control():
    p = copy.deepcopy(prot); del p['negative_controls']['wrong_neighbour']; return p


def prot_aux_training():
    p = copy.deepcopy(prot); p['training']['eligible_slices'] = 'primary+auxiliary'; return p


def prot_wrong_floor_hash():
    p = copy.deepcopy(prot); p['identity_by_hash']['fixed_now']['surface_floor_sha256'] = '0' * 64; return p


def prot_validated_word():
    p = copy.deepcopy(prot); p['limits'] = p['limits'] + ['the result is validated']; return p


expect_fail('protocol_threshold_changed', lambda: V.check_protocol(prot_threshold(), man, bands, floor, hashes))
expect_fail('protocol_muscle_offset_changed', lambda: V.check_protocol(prot_muscle_offset(), man, bands, floor, hashes))
expect_fail('protocol_control_missing', lambda: V.check_protocol(prot_missing_control(), man, bands, floor, hashes))
expect_fail('protocol_auxiliary_training', lambda: V.check_protocol(prot_aux_training(), man, bands, floor, hashes))
expect_fail('protocol_floor_hash', lambda: V.check_protocol(prot_wrong_floor_hash(), man, bands, floor, hashes))


def prot_rn_reference_changed():
    q = copy.deepcopy(prot); q['criteria']['cartilage']['required_neighbour']['reference_median_mm'] = 1.5
    q['criteria']['cartilage']['required_neighbour']['median_mm_max'] = round(1.5 + 0.9419, 4); return q


def prot_freeze_instant_date_only():
    q = copy.deepcopy(prot); q['applicability']['training_started_after'] = '2026-09-20'; return q


expect_fail('protocol_required_neighbour_reference_changed', lambda: V.check_protocol(prot_rn_reference_changed(), man, bands, floor, hashes))
expect_fail('protocol_freeze_instant_without_time', lambda: V.check_protocol(prot_freeze_instant_date_only(), man, bands, floor, hashes))


def classes_ignored():
    c = copy.deepcopy(classes); c['ignored_slices'] -= 1; return c


expect_fail('classes_ignored_count', lambda: V.check_classes(classes_ignored(), man))

ok = all(results.values())
print(json.dumps({'cases': len(results), 'all_as_expected': ok, 'failed': [k for k, v in results.items() if not v]}))
sys.exit(0 if ok else 1)
