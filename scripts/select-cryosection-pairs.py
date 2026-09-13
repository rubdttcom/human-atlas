"""Explicit selection of Denver slice <-> NLM photograph pairs for the RGB pilot (plan B stage 0 -> 2).

Reads transforms/nlm-cryosection-to-vhf.json and writes generated/cryosection-pair-selection.json. The policy is
declared here, versioned, and applied the same way to every slice; nothing is selected silently:

  pairs-v1
    quarantined (registry/cryosection-quarantine.json) -> excluded-observability, whatever the identity status: the tissue
                                    under the original labels is not observable in the photograph (block face frost, damage)
    settled                      -> usable          (label card and whole frame chose the same photograph)
    frame-with-margin            -> usable-flagged  (no card in the Denver crop; frame margin >= 0.005; the flag travels
                                                     with the pair so a consumer can restrict itself to settled pairs)
    provisional-block-consistent -> excluded        (frame margin below 0.005: the photograph is one of the ambiguity set,
                                                     1/3 mm apart; block consistency does not resolve it)
    unresolved                   -> excluded
    Denver blank slices          -> no-reference    (Denver has no image there; not a pair)

Excluded and flagged slices are listed with their ambiguity sets so a later rule (a different criterion, not a lower
threshold) can resolve them and be checked. Nothing here is anatomy.
"""
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSFORM = ROOT / 'transforms/nlm-cryosection-to-vhf.json'
QUARANTINE = ROOT / 'registry/cryosection-quarantine.json'
OUT = ROOT / 'generated/cryosection-pair-selection.json'
POLICY = {'id': 'pairs-v1', 'observability_first': 'a slice in registry/cryosection-quarantine.json is excluded-observability before any identity rule; identity never overrides it',
          'usable': ['settled'], 'usable_flagged': ['frame-with-margin'], 'excluded': ['provisional-block-consistent', 'unresolved'],
          'statement': 'identity status decides; the in-plane residual never promotes a slice; block consistency resolves nothing; thresholds are those of the transform and are not tuned here'}


def select(doc, quarantine):
    per = doc['per_slice']
    qk = {e['k']: e for e in quarantine['entries'] if e['status'] == 'quarantined'}
    missing = sorted(set(qk) - {p['k'] for p in per} - set(doc['denver_blank_slices']))
    if missing:
        raise SystemExit('quarantine names Denver slices absent from the transform: %s' % missing)
    known = set(POLICY['usable']) | set(POLICY['usable_flagged']) | set(POLICY['excluded'])
    unknown = sorted({p['identity_status'] for p in per} - known)
    if unknown:
        raise SystemExit('identity statuses without a policy rule: %s' % unknown)
    usable, flagged, excluded, quarantined = [], [], [], []
    for p in per:
        rec = {'k': p['k'], 'n': p['n'], 'nlm': p['nlm'], 'region': p['region'], 'identity_status': p['identity_status'],
               'frame_margin': p.get('frame_margin'), 'label_margin': p.get('label_margin'), 'residual_mean_nlm_px': p['residual_mean_nlm_px']}
        if p['k'] in qk:
            e = qk[p['k']]
            rec['reason'] = e['reason']; rec['source'] = e['source']; rec['photo_compressed_sha256'] = e['photo_compressed_sha256']; rec['denver_sha256'] = e['denver_sha256']
            quarantined.append(rec); continue
        if p['identity_status'] in POLICY['usable']:
            usable.append(rec)
        elif p['identity_status'] in POLICY['usable_flagged']:
            rec['flag'] = 'frame-only'; rec['ambiguity_set_nlm'] = p.get('ambiguity_set_nlm'); flagged.append(rec)
        else:
            rec['reason'] = p['resolution']; rec['ambiguity_set_nlm'] = p.get('ambiguity_set_nlm'); rec['ambiguity_span_mm'] = p.get('ambiguity_span_mm'); excluded.append(rec)
    if len(usable) + len(flagged) + len(excluded) + len(quarantined) != len(per):
        raise SystemExit('selection does not partition the per-slice table')
    per_region = {}
    for g in doc['regions']:
        rows = [p for p in per if p['region'] == g['region']]
        per_region[str(g['region'])] = {'k_first': g['k_first'], 'k_last': g['k_last'], 'slices': len(rows),
                                        'excluded_observability': sum(1 for p in rows if p['k'] in qk),
                                        'usable': sum(1 for p in rows if p['k'] not in qk and p['identity_status'] in POLICY['usable']),
                                        'usable_flagged': sum(1 for p in rows if p['k'] not in qk and p['identity_status'] in POLICY['usable_flagged']),
                                        'excluded_identity': sum(1 for p in rows if p['k'] not in qk and p['identity_status'] in POLICY['excluded'])}
    return {
        'policy': POLICY,
        'source': {'transform': str(TRANSFORM.relative_to(ROOT)), 'transform_sha256': hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest(),
                   'quarantine': str(QUARANTINE.relative_to(ROOT)), 'quarantine_sha256': hashlib.sha256(json.dumps(quarantine, sort_keys=True).encode()).hexdigest(), 'quarantine_version': quarantine['version'],
                   'report_sha256': doc['evidence']['report_sha256'], 'date': date.today().isoformat()},
        'counts': {'usable': len(usable), 'usable_flagged': len(flagged), 'excluded_identity': len(excluded), 'excluded_observability': len(quarantined), 'no_reference_blank_denver': len(doc['denver_blank_slices']),
                   'total_denver_slices': len(per) + len(doc['denver_blank_slices'])},
        'per_region': per_region,
        'usable_k': [r['k'] for r in usable],
        'usable_flagged': flagged,
        'excluded_identity': excluded,
        'excluded_observability': quarantined,
        'no_reference_blank_denver_k': doc['denver_blank_slices'],
        'limits': ['a usable pair means the photograph identity is settled by two criteria, the slice is not quarantined for observability, and the in-plane similarity residual is below 1 px; it says nothing about Denver label quality or anatomy',
                   'quarantine covers the checked block-boundary bands and reviewer findings; a usable slice elsewhere was not inspected for observability',
                   'usable-flagged pairs rest on the whole frame alone; consumers that need two criteria restrict themselves to usable_k',
                   'excluded slices are not wrong: their photograph is one of the ambiguity set, unresolved by this procedure'],
    }


def main():
    doc = json.loads(TRANSFORM.read_text())
    sel = select(doc, json.loads(QUARANTINE.read_text()))
    OUT.write_text(json.dumps(sel, indent=1))
    print(json.dumps({'done': True, 'out': str(OUT.relative_to(ROOT)), 'counts': sel['counts'], 'per_region': sel['per_region']}))


if __name__ == '__main__':
    main()
