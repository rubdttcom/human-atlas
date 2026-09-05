"""Render auditable report summaries from generated machine-readable evidence."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text())


def write(name, text):
    (ROOT / name).write_text(text + '\n')


summary = read('generated/coverage-summary.json')
coverage = '\n'.join([
    '# Imported-source coverage', '',
    '| Metric | Count |', '| --- | ---: |',
    *[f'| {key} | {summary[key]} |' for key in ['canonical_catalog_entries', 'source_meshes', 'female_measured',
       'registered_female', 'female_segmented_unreviewed', 'female_reference', 'template_only', 'without_direct_geometry']],
    '', 'Counts describe the imported source union, not all human anatomy. Hierarchy concepts without direct geometry are included.',
    'CT labels may group many structures; HRA assembly sex does not establish each component donor sex.',
    '', *['- ' + limitation for limitation in summary['limitations']],
])
write('generated/coverage-report.md', coverage)
write('docs/COVERAGE.md', coverage)
with (ROOT / 'datasets.csv').open() as handle:
    sources = list(csv.DictReader(handle))
write('docs/DATASETS.md', '\n'.join([
    '# Dataset inventory', '',
    'Candidate status is not proof of import. Detailed metadata and open questions are in `datasets.csv`.', '',
    '| Source | Sex | Donor | Licence position | Priority |', '| --- | --- | --- | --- | --- |',
    *[f"| [{s['name']}]({s['url']}) | {s['sex']} | {s['donor_id']} | {s['license']} | {s['priority']} |" for s in sources],
    '', 'Imported: HRA female, BodyParts3D male, TCIA 003 published segmentations and the Denver VHF final STL models (128 lower-limb meshes).',
    'BMFToolkit is inventoried but not shipped. Denver assets sit behind a Cloudflare challenge: plain HTTP clients get HTTP 403, so `scripts/fetch-denver.py` uses a local Chrome session. All other candidate imports remain pending.',
]))
registration = read('generated/registration-report.json')
write('generated/registration-report.md', '\n'.join([
    '# Experimental registration', '',
    f"Torso RMS: {registration['rms_mm']:.2f} mm. Maximum residual: {registration['max_residual_mm']:.2f} mm.",
    f"Global scale: {registration['scale']:.6f}. Volume factor: {registration['volume_scale']:.6f}.",
    '', '| Source proxy | Target label | Residual mm |', '| --- | --- | ---: |',
    *[f"| {p['source_concept']} | {p['target_label']} | {p['residual_mm']:.2f} |" for p in registration['landmarks']],
    '', *[line for fit in registration.get('additional_source_transforms', []) for line in [
        f"## {fit['from']} -> {fit['to']}", '',
        f"RMS: {fit['rms_mm']:.2f} mm. Maximum residual: {fit['max_residual_mm']:.2f} mm. Scale: {fit['scale']:.6f}. Volume factor: {fit['volume_scale']:.6f}.", '',
        '| Source proxy | Target label | Residual mm |', '| --- | --- | ---: |',
        *[f"| {p['source_concept']} | {p['target_label']} | {p['residual_mm']:.2f} |" for p in fit['landmarks']], '',
        *['- ' + limitation for limitation in fit['limitations']], '']],
    'The head uses a separate bounding-box fit. Its bounds containment is not an anatomical validation.',
    'No Hausdorff distance, manual landmarks or cervical continuity validation has been completed.',
    'Matrices and regional scale changes are in `registration-report.json`. The frame is TCIA 003, not canonical VHF.',
]))
licence = read('generated/licence-report-open-clean.json')
write('generated/licence-report.md', '\n'.join([
    '# Shipped-geometry licence report', '',
    f"Target: {licence['target']}. Mesh references audited: {licence['mesh_references']}. Errors: {len(licence['errors'])}.",
    'HRA, BodyParts3D, TCIA segmentations and Denver VHF models are recorded as CC BY 4.0 with source links and attribution.',
    'Candidate sources are not approved by this result. Per-asset unknowns remain excluded from the shipped atlases.',
    'This report checks recorded licence compatibility and traceability, not anatomical quality.',
]))
qa = read('generated/qa-report.json')['structures']
write('generated/qa-report.md', '\n'.join([
    '# Geometry QA', '', '| Atlas | Meshes | Open boundaries | Nonmanifold edges | Degenerate triangles |',
    '| --- | ---: | ---: | ---: | ---: |',
    *[f"| {atlas} | {len(rows)} | {sum(r['boundary_edges'] > 0 for r in rows)} | {sum(r['nonmanifold_edges'] > 0 for r in rows)} | {sum(r['degenerate_faces'] > 0 for r in rows)} |"
      for atlas in sorted({r['atlas'] for r in qa}) for rows in [[r for r in qa if r['atlas'] == atlas]]],
    '', 'Issue columns count meshes affected. Individual values are in `qa-report.json`.',
    'Self-intersections and anatomical review remain unassessed. Open boundaries can be intentional for anatomical surfaces.',
]))
print('Wrote dataset, coverage, registration, licence and geometry summaries.')
