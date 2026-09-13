"""Regression test for scripts/build-cryosection-transform.py (Codex audit of 02d3f59, two P2 findings).

In-memory corruptions of the shipped alignment report; the builder must refuse each one and must keep the identity
status of every slice in the transform it does build. Nothing is written.
"""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bct', ROOT / 'scripts/build-cryosection-transform.py')
bct = importlib.util.module_from_spec(spec); spec.loader.exec_module(bct)
rep = json.loads((ROOT / 'generated/cryosection-alignment-check.json').read_text())


def expect_refusal(name, mutate):
    r = copy.deepcopy(rep); mutate(r)
    try:
        bct.build(r)
    except SystemExit as e:
        print(f'ok: {name} -> refused ({str(e).splitlines()[1].strip()[:90]})'); return True
    print(f'FAIL: {name} -> built a transform'); return False


results = []
results.append(expect_refusal('report truncated to k 2500..2519 (still step 1)', lambda r: r['slices'].__setitem__(slice(None), [s for s in r['slices'] if 2500 <= s['k'] <= 2519])))
results.append(expect_refusal('one Denver slice missing', lambda r: r['slices'].pop(1500)))
results.append(expect_refusal('one Denver slice duplicated', lambda r: r['slices'].append(copy.deepcopy(r['slices'][1500]))))
results.append(expect_refusal('step != 1', lambda r: r['summary'].__setitem__('step', 25)))
def _fail_status(r):
    s = next(x for x in r['slices'] if x['status'] == 'matched'); s['status'] = 'no-nlm-slice'
    r['summary']['statuses'] = dict(r['summary']['statuses']); r['summary']['statuses']['matched'] -= 1; r['summary']['statuses']['no-nlm-slice'] = 1; r['summary']['matched'] -= 1
results.append(expect_refusal('an unresolved slice status', _fail_status))
def _dup_photo(r):
    a, b = [x for x in r['slices'] if x['status'] == 'matched'][100:102]; b['n_best'] = a['n_best']; b['offset_best'] = b['n_best'] + b['k']
results.append(expect_refusal('two Denver slices on one photograph', _dup_photo))
def _offset_incons(r):
    a = [x for x in r['slices'] if x['status'] == 'matched'][200]; a['offset_best'] += 1
results.append(expect_refusal('offset_best inconsistent with n_best', _offset_incons))

def _counts_mismatch(r):
    r['summary']['statuses'] = dict(r['summary']['statuses']); r['summary']['statuses']['matched'] -= 1
results.append(expect_refusal('summary counts disagree with the rows', _counts_mismatch))

doc = bct.build(copy.deepcopy(rep))
per = doc['per_slice']
frame_only = [p for p in per if p['identity_by'] == 'frame']
weak = [p for p in per if p['provisional']]
ok = all('identity_status' in p and 'frame_margin' in p and 'resolution' in p for p in per)
ok &= all(p['identity_status'] == 'settled' for p in per if p['identity_by'] == 'label' and p['label_and_frame_agree'])
ok &= all(p['identity_status'] in ('frame-with-margin', 'provisional-block-consistent', 'unresolved') for p in frame_only)
ok &= doc['identity']['provisional_slices'] == len(weak)
ok &= sum(g['identity_status_counts'].get('provisional-block-consistent', 0) for g in doc['regions']) == sum(1 for p in weak if p['identity_status'] == 'provisional-block-consistent')
ok &= len(per) + len(doc['denver_blank_slices']) == bct.DEN_N
print(f"{'ok' if ok else 'FAIL'}: identity kept per slice; frame-only {len(frame_only)}, provisional {len(weak)}, status counts {doc['identity']['status_counts']}")
results.append(ok)
# a weak whole-frame margin must survive into the transform and be excluded by the declared pair policy
spec2 = importlib.util.spec_from_file_location('scp', ROOT / 'scripts/select-cryosection-pairs.py')
scp = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(scp)
r2 = copy.deepcopy(rep)
victim = next(x for x in r2['slices'] if x['status'] == 'matched' and x['identity_by'] == 'frame' and x['frame_choice']['margin'] >= 0.01)
victim['frame_choice']['margin'] = 0.001            # weaken the margin of a frame-only slice
doc2 = bct.build(r2)
p2 = next(p for p in doc2['per_slice'] if p['k'] == victim['k'])
sel2 = scp.select(doc2)
ok2 = p2['identity_status'] == 'provisional-block-consistent' and p2['provisional'] and p2['frame_margin'] == 0.001 and 'ambiguity_set_n' in p2
ok2 &= victim['k'] in {e['k'] for e in sel2['excluded']} and victim['k'] not in set(sel2['usable_k'])
ok2 &= sel2['counts']['excluded'] == doc2['identity']['provisional_slices']
print(f"{'ok' if ok2 else 'FAIL'}: weakened frame margin on k={victim['k']} survives to the transform (provisional, ambiguity set {p2.get('ambiguity_set_nlm')}) and is excluded by {sel2['policy']['id']}")
results.append(ok2)
# a label-settled slice cannot be demoted or promoted by residual: set a large residual, status stays settled and selection unchanged
r3 = copy.deepcopy(rep)
lab = next(x for x in r3['slices'] if x['status'] == 'matched' and x['identity_by'] == 'label' and x['label_and_frame_agree'])
lab['local_residual']['mean_nlm_px'] = 0.4
doc3 = bct.build(r3); p3 = next(p for p in doc3['per_slice'] if p['k'] == lab['k'])
ok3 = p3['identity_status'] == 'settled' and p3['residual_mean_nlm_px'] == 0.4
print(f"{'ok' if ok3 else 'FAIL'}: identity status does not depend on the in-plane residual")
results.append(ok3)
sel = scp.select(doc)
ok4 = sel['counts']['usable'] + sel['counts']['usable_flagged'] + sel['counts']['excluded'] + sel['counts']['no_reference_blank_denver'] == bct.DEN_N \
    and sel['counts']['excluded'] == doc['identity']['provisional_slices'] and all(e.get('ambiguity_set_nlm') for e in sel['excluded'])
print(f"{'ok' if ok4 else 'FAIL'}: pair selection partitions all {bct.DEN_N} Denver slices: {sel['counts']}")
results.append(ok4)
print(json.dumps({'cases': len(results), 'all_as_expected': all(results)}))
raise SystemExit(0 if all(results) else 1)
