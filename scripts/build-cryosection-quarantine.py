"""Build registry/cryosection-quarantine.json: slices excluded from RGB-label pairs for observability, independent of identity.

Sources: the curated seed (registry/cryosection-quarantine-seed.json, reviewer findings with evidence) and the band
metric (generated/cryosection-observability-band.json, flagged slices near the block boundaries). Every entry carries the
Denver slice hash (from the alignment report) and the photograph hash (from the band report or the inventory), the
reason, the source and the evidence. Quarantined slices are `ignore`, never background; nothing is deleted or edited.
The pair selection (scripts/select-cryosection-pairs.py) applies this registry before the identity policy.
"""
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'registry/cryosection-quarantine-seed.json'
BAND = ROOT / 'generated/cryosection-observability-band.json'
ALIGN = ROOT / 'generated/cryosection-alignment-check.json'
INVENTORY = ROOT / 'generated/cryosection-inventory.json'
OUT = ROOT / 'registry/cryosection-quarantine.json'


def build(seed, band, align, inventory):
    den_sha = {r['k']: r.get('denver_sha256') for r in align['slices']}
    nlm_of_k = {r['k']: r.get('nlm_best') for r in align['slices'] if r['status'] == 'matched'}
    inv_sha = {r['file']: r['sha256'] for r in inventory['files']}
    band_rows = {r['k']: r for r in band['rows'] if r['status'] == 'measured'}
    entries = {}
    for e in seed['entries']:
        if nlm_of_k.get(e['k']) != e['nlm']:
            raise SystemExit('seed k=%d names %s but the alignment report matched %s' % (e['k'], e['nlm'], nlm_of_k.get(e['k'])))
        entries[e['k']] = {**e, 'status': 'quarantined', 'denver_sha256': den_sha[e['k']], 'photo_compressed_sha256': inv_sha[e['nlm']],
                           'band_metric': {k: band_rows[e['k']][k] for k in ('fraction_non_tissue', 'fraction_block_like', 'fraction_dark', 'fraction_frost_like')} if e['k'] in band_rows else None}
    for name, b in band['summary']['bands'].items():
        for k in b['flagged_k']:
            if k in entries:
                entries[k]['also_flagged_by_band'] = name; continue
            r = band_rows[k]
            entries[k] = {'k': k, 'nlm': r['nlm'], 'status': 'quarantined', 'source': 'observability-band-metric', 'band': name,
                          'reason': 'non-tissue fraction under the original labels %.3f above the band threshold %.3f' % (r['fraction_non_tissue'], b['baseline_non_tissue']['threshold']),
                          'denver_sha256': den_sha[k], 'photo_compressed_sha256': inv_sha[r['nlm']],
                          'band_metric': {kk: r[kk] for kk in ('fraction_non_tissue', 'fraction_block_like', 'fraction_dark', 'fraction_frost_like')}}
    return {'id': 'cryosection-quarantine', 'version': 1, 'date': date.today().isoformat(),
            'rule': 'exclusion by observability of the tissue under the original labels, independent of the photograph identity status; quarantined slices are ignore (never background) in any RGB-label pairing; originals untouched; a later regional mask may recover observable tissue by a documented rule',
            'sources': {'seed': str(SEED.relative_to(ROOT)), 'band_report': str(BAND.relative_to(ROOT)), 'band_report_sha256': hashlib.sha256(BAND.read_bytes()).hexdigest(),
                        'band_rule': band['summary']['rule'], 'bands_checked': {n: b['k_range'] for n, b in band['summary']['bands'].items()}},
            'entries': [entries[k] for k in sorted(entries)],
            'limits': ['only the checked bands were measured; slices elsewhere are not thereby clean', 'colour thresholds delimit the extent; the seed entries are reviewer observations, not anatomy']}


def main():
    doc = build(json.loads(SEED.read_text()), json.loads(BAND.read_text()), json.loads(ALIGN.read_text()), json.loads(INVENTORY.read_text()))
    OUT.write_text(json.dumps(doc, indent=1))
    print(json.dumps({'done': True, 'out': str(OUT.relative_to(ROOT)), 'quarantined_k': [e['k'] for e in doc['entries']]}))


if __name__ == '__main__':
    main()
