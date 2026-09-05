"""Verify the curated ontology crosswalk against OLS and record the evidence per term.

Input : registry/crosswalk-proposals.json (curated dataset-label -> UBERON/FMA proposals).
Output: registry/ontology-crosswalk-reviewed.json, one entry per source label with the
        OLS record (IRI, label, synonyms, xrefs, definition), the match type actually
        observed (exact label, exact synonym or curated equivalent), the derived UBERON and
        FMA identifiers, and a review status. No identifier is guessed: a proposal whose
        term cannot be retrieved from OLS is written as `unresolved` and never applied.

HRA female lateralized FMA terms ("Left femur", "Articular cartilage of distal epiphysis of
left femur") are resolved to their generic FMA parent through the OLS hierarchy and mapped to
UBERON only when the UBERON term lists that FMA identifier as a cross-reference.

Usage: .venv/bin/python scripts/build-crosswalk.py [--offline]
--offline reuses the cached OLS records in generated/ols-cache.json (for reproducible rebuilds).
"""
import argparse
import json
import re
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OLS = 'https://www.ebi.ac.uk/ols4/api'
CACHE_PATH = ROOT / 'generated/ols-cache.json'
parser = argparse.ArgumentParser()
parser.add_argument('--offline', action='store_true')
args = parser.parse_args()
cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
session = requests.Session()
proposals = json.loads((ROOT / 'registry/crosswalk-proposals.json').read_text())
hra = json.loads((ROOT / 'public/models/atlas-female.json').read_text())


def get(url, params=None):
    key = url + '?' + json.dumps(params or {}, sort_keys=True)
    if key in cache:
        return cache[key]
    if args.offline:
        raise SystemExit(f'Offline and not cached: {key}')
    for attempt in range(5):
        response = session.get(url, params=params, timeout=60)
        if response.status_code in (200, 404):
            break
        time.sleep(2 ** attempt)
    if response.status_code == 404:
        # OLS answers 404 for identifiers absent from its FMA/UBERON release; recorded as "no term".
        cache[key] = {'_embedded': {'terms': []}, 'http_status': 404}
        return cache[key]
    response.raise_for_status()
    cache[key] = response.json()
    return cache[key]


def ontology_of(term):
    return 'uberon' if term.startswith('UBERON:') else 'fma'


def normalize_fma(term):
    match = re.match(r'^(?:FMA:?|fma)(\d+)$', term)
    return f'FMA:{match.group(1)}' if match else term


def term_record(term):
    """OLS term record for a UBERON obo_id or an FMA short form."""
    ontology = ontology_of(term)
    params = {'obo_id': term} if ontology == 'uberon' else {'short_form': 'fma' + normalize_fma(term)[4:]}
    data = get(f'{OLS}/ontologies/{ontology}/terms', params)
    terms = data.get('_embedded', {}).get('terms', [])
    if not terms:
        return None
    entry = terms[0]
    xrefs = entry.get('obo_xref') or []
    return {'id': normalize_fma(term) if ontology == 'fma' else entry['obo_id'], 'iri': entry['iri'], 'label': entry['label'],
            'ontology': ontology, 'synonyms': entry.get('synonyms') or [], 'definition': (entry.get('description') or [None])[0],
            'obsolete': bool(entry.get('is_obsolete')),
            'xrefs': [f"{x['database']}:{x['id']}" for x in xrefs if x.get('database') and x.get('id')],
            'ols_url': f'{OLS}/ontologies/{ontology}/terms?' + '&'.join(f'{k}={v}' for k, v in params.items()),
            'parents_url': entry['_links'].get('parents', {}).get('href')}


def match_type(label, record):
    if label is None:
        return 'curated-equivalent'
    wanted = label.lower().strip()
    if record['label'].lower() == wanted:
        return 'exact-label'
    if wanted in {s.lower() for s in record['synonyms']}:
        return 'exact-synonym'
    return 'curated-equivalent'


def uberon_for_fma(fma_id, generic_label):
    """UBERON term whose label matches and which cross-references the FMA id; None otherwise."""
    search = get(f'{OLS}/search', {'q': generic_label, 'ontology': 'uberon', 'exact': 'true', 'rows': 10, 'fieldList': 'obo_id,label'})
    for doc in search['response']['docs']:
        if not doc.get('obo_id', '').startswith('UBERON:'):
            continue
        record = term_record(doc['obo_id'])
        if record and fma_id in record['xrefs']:
            return record
    return None


def fma_for_uberon(record):
    return next((x for x in record['xrefs'] if x.startswith('FMA:')), None)


retrieved = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
entries = []
STATUS_OK = 'evidence-matched (OLS); anatomist review pending'

def searched_term(label):
    """UBERON term whose label equals `label` exactly (defining ontology only); None unless unique."""
    search = get(f'{OLS}/search', {'q': label, 'ontology': 'uberon', 'exact': 'true', 'rows': 10, 'fieldList': 'obo_id,label,is_defining_ontology'})
    hits = [d['obo_id'] for d in search['response']['docs'] if d.get('is_defining_ontology') and d.get('label', '').lower() == label.lower() and d.get('obo_id', '').startswith('UBERON:')]
    return hits[0] if len(set(hits)) == 1 else None


# 1. Denver VHF, TCIA and NLM CT curated proposals (fixed term, or an exact UBERON label to search).
for source in ('denver-vhf', 'tcia', 'nlm-vhf-ct'):
    for label, proposal in proposals.get(source, {}).items():
        term = proposal.get('term') or (searched_term(proposal['search_label']) if proposal.get('search_label') else None)
        entry = {'source': source, 'source_label': label, 'proposed_term': term or proposal.get('search_label'), 'granularity': proposal.get('granularity', 'individual'),
                 'laterality': proposal.get('laterality'), 'notes': proposal.get('notes'), 'retrieved_at': retrieved}
        record = term_record(term) if term else None
        if record is None or record['obsolete']:
            entry.update({'review_status': 'unresolved: term not retrievable from OLS or obsolete; mapping not applied', 'applied': False})
            entries.append(entry)
            continue
        uberon_id = record['id'] if record['ontology'] == 'uberon' else None
        fma_id = fma_for_uberon(record) if record['ontology'] == 'uberon' else record['id']
        if record['ontology'] == 'uberon' and proposal.get('fma_equivalent'):
            declared = normalize_fma(proposal['fma_equivalent'])
            fma_record = term_record(declared)
            entry['fma_equivalent_check'] = {'declared': declared, 'label': fma_record['label'] if fma_record else None,
                                             'confirmed_by_uberon_xref': declared in record['xrefs']}
            fma_id = fma_id or declared
        status = STATUS_OK if proposal.get('status', 'apply') == 'apply' else 'proposed-uncertain; mapping not applied pending review'
        entry.update({'canonical_term': record['id'], 'term': record, 'match_type': match_type(proposal.get('match_label') or proposal.get('search_label'), record),
                      'uberon_id': uberon_id, 'fma_id': fma_id, 'review_status': status, 'applied': status == STATUS_OK})
        entries.append(entry)

# 2. Lateralized FMA identifiers (HRA female and BodyParts3D) -> generic FMA -> UBERON (xref-confirmed).
SIDE = re.compile(r'^(Left|Right) (.+)$|^(.+) of (left|right) (.+)$|^(.+) \((left|right)\)$', re.I)
bodyparts = json.loads((ROOT / 'public/models/atlas.json').read_text())


def lateral_entry(source, concept):
    record = term_record(concept)
    if record is None:
        return {'source': source, 'source_label': concept, 'review_status': 'unresolved: FMA term not retrievable from OLS', 'applied': False, 'retrieved_at': retrieved}
    match = SIDE.match(record['label'])
    if not match:
        return None
    groups = [g for g in match.groups() if g]
    side = next(g for g in groups if g.lower() in ('left', 'right')).lower()
    generic_label = ' '.join(g for g in groups if g.lower() not in ('left', 'right')).strip()
    if ' of ' in record['label'] and not record['label'].lower().startswith(side):
        generic_label = re.sub(r' of (left|right) ', ' of ', record['label'], flags=re.I)
    parents = get(record['parents_url']).get('_embedded', {}).get('terms', []) if record['parents_url'] else []
    generic = next((p for p in parents if p['label'].lower() == generic_label.lower()), None)
    entry = {'source': source, 'source_label': concept, 'source_term_label': record['label'], 'laterality': side, 'retrieved_at': retrieved,
             'generic_label_expected': generic_label, 'parents': [{'id': normalize_fma(p['short_form']), 'label': p['label']} for p in parents]}
    if generic is None:
        entry.update({'review_status': 'unresolved: no FMA parent with the side-neutral label; mapping not applied', 'applied': False})
        return entry
    generic_id = normalize_fma(generic['short_form'])
    uberon = uberon_for_fma(generic_id, generic['label'])
    entry.update({'generic_fma': {'id': generic_id, 'label': generic['label']}, 'fma_id': generic_id,
                  'uberon_id': uberon['id'] if uberon else None, 'canonical_term': uberon['id'] if uberon else generic_id,
                  'term': uberon or term_record(generic_id), 'match_type': 'fma-parent' + ('; uberon-xref-confirmed' if uberon else '; no uberon xref'),
                  'review_status': STATUS_OK, 'applied': True})
    return entry


import concurrent.futures
for source, atlas in (('hra-female', hra), ('bodyparts3d', bodyparts)):
    concepts = sorted({normalize_fma(p['conceptId']) for p in atlas['parts'] if re.match(r'^FMA:?\d+$', p['conceptId'])})
    with concurrent.futures.ThreadPoolExecutor(1 if args.offline else 6) as pool:
        results = list(pool.map(lambda c: lateral_entry(source, c), concepts))
    entries.extend(e for e in results if e)
    print(f'{source}: {len(concepts)} FMA concepts examined, {sum(1 for e in results if e)} lateralized', flush=True)

CACHE_PATH.parent.mkdir(exist_ok=True)
CACHE_PATH.write_text(json.dumps(cache, indent=1, ensure_ascii=False) + '\n')
summary = {'entries': len(entries), 'applied': sum(e['applied'] for e in entries),
           'by_source': {s: {'entries': sum(e['source'] == s for e in entries), 'applied': sum(e['source'] == s and e['applied'] for e in entries),
                             'exact_label': sum(e['source'] == s and e.get('match_type') == 'exact-label' for e in entries),
                             'exact_synonym': sum(e['source'] == s and e.get('match_type') == 'exact-synonym' for e in entries),
                             'curated_equivalent': sum(e['source'] == s and e.get('match_type') == 'curated-equivalent' for e in entries),
                             'uberon': sum(e['source'] == s and bool(e.get('uberon_id')) for e in entries),
                             'fma_only': sum(e['source'] == s and e['applied'] and not e.get('uberon_id') for e in entries)}
                         for s in ('denver-vhf', 'tcia', 'nlm-vhf-ct', 'hra-female', 'bodyparts3d')},
           'unresolved_or_uncertain': [f"{e['source']}:{e['source_label']}: {e['review_status']}" for e in entries if not e['applied']],
           'method': 'OLS4 term records (label, synonyms, xrefs, definition) retrieved and stored per entry; lateralized FMA resolved via OLS parents; UBERON accepted only with FMA xref confirmation.',
           'anatomist_review': 'pending for every entry', 'retrieved_at': retrieved}
(ROOT / 'registry/ontology-crosswalk-reviewed.json').write_text(json.dumps({'summary': summary, 'entries': entries}, indent=2, ensure_ascii=False) + '\n')
print(json.dumps(summary, indent=2, ensure_ascii=False))
