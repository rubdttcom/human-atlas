"""Regression test for validate-consensus-metadata.py: corrupted bone-candidate fields must fail the validator.

Reproduces the Codex audit of f28467f (12 September 2026): the validator accepted an in-memory copy of
public/atlases/ct-consensus.json with versus_nlm_vhf_ct_label=None, empty correspondence pairs and a Denver p95 of 999 mm.
Nothing is written; the shipped files are read through a patched Path.read_text and altered only in memory.

Usage: .venv/bin/python scripts/test-consensus-metadata.py
"""
import contextlib
import io
import json
import runpy
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / 'scripts/validate-consensus-metadata.py'
ATLAS = (ROOT / 'public/atlases/ct-consensus.json').resolve()
MANIFEST = (ROOT / 'manifests/ct-consensus.json').resolve()
REAL_READ_TEXT = Path.read_text


def run(mutate_atlas=None, mutate_manifest=None, families=('bones',)):
    def read_text(self, *a, **k):
        text = REAL_READ_TEXT(self, *a, **k)
        if mutate_atlas and self.resolve() == ATLAS:
            data = json.loads(text)
            for p in data['parts']:
                if p['provenance']['instance_family'] in families:
                    mutate_atlas(p['provenance'])
            return json.dumps(data)
        if mutate_manifest and self.resolve() == MANIFEST:
            data = json.loads(text)
            for r in data:
                if r.get('instance_family') == 'bones':
                    mutate_manifest(r)
            return json.dumps(data)
        return text
    out = io.StringIO()
    with mock.patch.object(Path, 'read_text', read_text), contextlib.redirect_stdout(out):
        try:
            runpy.run_path(str(VALIDATOR), run_name='__main__')
        except SystemExit as e:
            return False, str(e), out.getvalue()
    return True, '', out.getvalue()


def set_ct_none(prov):
    prov['versus_nlm_vhf_ct_label'] = None


def empty_pairs(prov):
    prov['gates']['geometric_correspondence']['pairs'] = {}


def denver_999(prov):
    if prov.get('versus_denver_mesh'):
        prov['versus_denver_mesh']['candidate_surface_to_denver_vertices_mm']['p95'] = 999


def denver_p50_over_p95(prov):
    if prov.get('versus_denver_mesh'):
        prov['versus_denver_mesh']['denver_vertices_to_candidate_surface_mm']['p50'] = 50.0


def flip_side(prov):
    if prov['gates']['laterality'].get('applicable'):
        prov['gates']['laterality']['per_model_side']['moose'] = 'right' if prov['laterality'] == 'left' else 'left'


def drop_denver_mesh(prov):
    prov['denver_mesh'] = None


def manifest_gate_fail(row):
    row['gates']['laterality']['passed'] = False


def shape_check_other_geometry(prov):
    prov['shape_check']['geometry_sha256'] = '0' * 64


def shape_check_flipped(prov):
    if prov['shape_check']['decision'] == 'above-denver-baseline':
        prov['shape_check']['decision'] = 'reaches-denver-baseline'; prov['shape_check']['passed'] = True


def shape_check_dropped(prov):
    prov['shape_check'] = None


def posture_dropped(prov):
    prov['posture_offset'] = None


def posture_shifted(prov):
    if prov.get('posture_offset') and prov['posture_offset'].get('relative_to_pelvis'):
        prov['posture_offset']['relative_to_pelvis']['norm'] = 0.0


def posture_other_report(prov):
    if prov.get('posture_offset'):
        prov['posture_offset']['report_sha256'] = '0' * 64


def posture_validated_wording(prov):
    if prov.get('posture_offset'):
        prov['posture_offset']['note'] = 'validated posture; nothing is corrected; nothing is anatomy'


INSTANCES = ('vertebrae', 'ribs_left', 'ribs_right')
cases = [
    ('unchanged files pass', None, None, True),
    ('versus_nlm_vhf_ct_label None', set_ct_none, None, False),
    ('empty correspondence pairs', empty_pairs, None, False),
    ('Denver p95 999 mm in the atlas only', denver_999, None, False),
    ('Denver p50 above p95', denver_p50_over_p95, None, False),
    ('one model on the other side', flip_side, None, False),
    ('Denver mesh dropped but comparison kept', drop_denver_mesh, None, False),
    ('manifest copy with a failed gate', None, manifest_gate_fail, False),
    ('shape check bound to another geometry', shape_check_other_geometry, None, False),
    ('shape check decision flipped to reaches-baseline', shape_check_flipped, None, False),
    ('shape check dropped', shape_check_dropped, None, False),
    ('posture offset dropped from the instances', posture_dropped, None, False, INSTANCES),
    ('posture relative offset zeroed in the atlas only', posture_shifted, None, False, INSTANCES),
    ('posture offset bound to another report', posture_other_report, None, False, INSTANCES),
    ('posture note reads as validation', posture_validated_wording, None, False, INSTANCES),
]
failures = []
for name, ma, mm, expect_ok, *fam in cases:
    ok, code, out = run(ma, mm, fam[0] if fam else ('bones',))
    status = 'ok' if ok == expect_ok else 'UNEXPECTED'
    if ok != expect_ok:
        failures.append(name)
    print(f'{status}: {name} -> validator {"passed" if ok else "failed"} {code}')
if failures:
    raise SystemExit(f'{len(failures)} cases did not behave as expected: {failures}')
print(json.dumps({'cases': len(cases), 'all_as_expected': True}))
