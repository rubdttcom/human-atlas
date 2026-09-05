"""Render auditable report summaries from generated machine-readable evidence."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text())


def write(name, text):
    (ROOT / name).write_text(text + '\n')


def exists(name):
    return (ROOT / name).exists()


summary = read('generated/coverage-summary.json')
coverage = '\n'.join([
    '# Imported-source coverage', '',
    '| Metric | Count |', '| --- | ---: |',
    *[f'| {key} | {summary[key]} |' for key in ['canonical_catalog_entries', 'source_meshes', 'female_measured', 'registered_female', 'female_ct_same_donor',
       'female_segmented_unreviewed', 'female_reference', 'template_only', 'without_direct_geometry', 'multi_source_entries', 'denver_hra_merged_entries', 'crosswalk_applied_meshes'] if key in summary],
    '', 'Counts describe the imported source union, not all human anatomy. Hierarchy concepts without direct geometry are included.',
    'CT labels may group many structures; HRA assembly sex does not establish each component donor sex.',
    '`female_ct_same_donor` counts entries covered by the NLM VHF CT labels (same donor as Denver, automatic segmentation).',
    '', *['- ' + limitation for limitation in summary['limitations']],
])
write('generated/coverage-report.md', coverage)
write('docs/COVERAGE.md', coverage)
with (ROOT / 'datasets.csv').open() as handle:
    sources = list(csv.DictReader(handle))
write('docs/DATASETS.md', '\n'.join([
    '# Dataset inventory', '',
    'Candidate status is not proof of import. Detailed metadata, verification dates and open questions are in `datasets.csv`.', '',
    '| Source | Sex | Donor | Licence position | Priority |', '| --- | --- | --- | --- | --- |',
    *[f"| [{s['name']}]({s['url']}) | {s['sex']} | {s['donor_id']} | {s['license']} | {s['priority']} |" for s in sources],
    '', 'Imported: HRA female, BodyParts3D male, TCIA 003 published segmentations, the Denver VHF final STL models (128 lower-limb meshes) and the',
    'TotalSegmentator labels of the NLM Visible Human Female fresh CT (same donor as Denver). BMFToolkit is compared locally but not shipped (data licence',
    'scope unconfirmed). Teeth3DS is CC BY-NC-ND and cannot be shipped in any target. Denver assets sit behind a Cloudflare challenge: plain HTTP clients get',
    'HTTP 403, so `scripts/fetch-denver.py` uses a local Chrome session. SPIDER, OpenEar and HiP-CT are verified CC BY 4.0 candidates awaiting specimen selection.',
]))

registration = read('generated/registration-report.json')
transforms = {t['id']: t for t in registration['transforms']}
hra_fit, nlm_fit, tcia_fit = transforms['hra-stage-to-vhf'], transforms['nlm-stage-to-vhf'], transforms['tcia003-stage-to-vhf']
acceptance = registration['acceptance']
nlm_ct = nlm_fit['components'][0]
nlm_report = read('generated/nlm-ct-registration.json') if exists('generated/nlm-ct-registration.json') else None


def distance_rows(entry):
    frame = entry.get('in_canonical_frame')
    if not frame:
        return [f"| {entry['structure']} | {entry['denver_to_tcia']['mean_mm']:.1f} | {entry['denver_to_tcia']['p95_mm']:.1f} | {entry['denver_to_tcia']['max_mm']:.1f} | n/a | n/a |"]
    shape = entry['shape_after_rigid_icp']['after_rigid_icp']
    return [f"| {entry['structure']} | {frame['a_to_b']['mean_mm']:.1f} | {frame['a_to_b']['p95_mm']:.1f} | {frame['hausdorff_mm']:.1f} | {entry['denver_inside_tcia_envelope']['fraction_inside']:.3f} | {shape['a_to_b']['p95_mm']:.1f} |"]


def acceptance_rows():
    rows = []
    for key, value in acceptance.items():
        if isinstance(value, dict) and 'met' in value:
            numbers = ', '.join(f'{k} {v:.3f}' if isinstance(v, float) else f'{k} {v}' for k, v in value.items() if k not in ('met', 'note', 'per_structure'))
            rows.append(f"- {key}: {'met' if value['met'] else 'not met'} ({numbers})" + (f" {value['note']}" if value.get('note') else ''))
    return rows


write('generated/registration-report.md', '\n'.join([
    '# Registration into canonical space VHF-image-2022 (composition 0.4)', '',
    f"Canonical space: {registration['canonical_space']['definition']}", f"Status: {registration['canonical_space']['status']}.",
    f"Composition: {registration['composition']['meshes_by_source']} meshes by source; {registration['composition']['meshes_by_donor']} by donor.", '',
    '## Same donor: NLM VHF fresh CT -> Denver frame', '',
    f"{nlm_ct['type']}. Rotation {nlm_ct['rotation_deg']:.2f} deg, scale fixed at 1.0, pelvis surface RMS {nlm_ct['rms_mm']:.2f} mm, p95 {nlm_ct['p95_mm']:.2f} mm, Hausdorff {nlm_ct['hausdorff_mm']:.1f} mm.",
    f"Frame verification: {nlm_fit['evidence']['axes_and_units']} (free-scale check {nlm_fit['evidence']['free_scale']:.4f}). {nlm_fit['evidence']['interpretation']}", '',
    '| Structure | CT->Denver mean mm | p95 mm | Hausdorff mm |', '| --- | ---: | ---: | ---: |',
    *[f"| {e['structure']} | {e['in_canonical_frame']['a_to_b']['mean_mm']:.1f} | {e['in_canonical_frame']['a_to_b']['p95_mm']:.1f} | {e['in_canonical_frame']['hausdorff_mm']:.1f} |" for e in nlm_fit['surface_distances']], '',
    *([f"Femur pose change between acquisitions (own rigid fit versus pelvis transform): " + ', '.join(f"{b['structure']} {b['pose_change_relative_to_pelvis']['rotation_deg']:.1f} deg" for b in nlm_report['bones'] if 'pose_change_relative_to_pelvis' in b) + '.'] if nlm_report else []),
    'CT labels are TotalSegmentator output (task total, Apache-2.0), not reviewed segmentations; Denver bones replace the CT hip bones, sacrum and femora in the composite.', '',
    f"## {hra_fit['from']} -> {hra_fit['to']}", '',
    f"{hra_fit['type']} on {hra_fit['landmark_selection']}. RMS {hra_fit['rms_mm']:.2f} mm, maximum {hra_fit['max_residual_mm']:.2f} mm, scale {hra_fit['scale']:.6f}.", '',
    '| Source proxy | Target CT labels | Residual mm |', '| --- | --- | ---: |',
    *[f"| {p['source_concept']} | {', '.join(p['target_labels'])} | {p['residual_mm']:.2f} |" for p in hra_fit['landmarks']], '',
    f"Cross-check, direct HRA pelvic landmark fit to Denver (not used): RMS {hra_fit['cross_checks'][0]['rms_mm']:.2f} mm, maximum {hra_fit['cross_checks'][0]['max_residual_mm']:.2f} mm, scale {hra_fit['cross_checks'][0]['scale']:.6f}. {hra_fit['cross_checks'][0]['interpretation']}", '',
    '| Organ proxy | Organ-fit offset vs CT mm | Direct pelvic offset vs CT mm |', '| --- | ---: | ---: |',
    *[f"| {o['proxy']} | {o['organ_fit_offset_mm']:.1f} | {o['direct_pelvic_offset_mm']:.1f} |" for o in hra_fit['cross_checks'][0]['organ_offsets_vs_ct_in_vhf']], '',
    *['- ' + limitation for limitation in hra_fit['limitations']], '',
    'The head uses a separate bounding-box fit into the CT brain envelope. Its bounds containment is not an anatomical validation.', '',
    f"## Alternative source: {tcia_fit['from']} -> {tcia_fit['to']} (not composed)", '',
    f"Pelvic landmark similarity: RMS {tcia_fit['rms_mm']:.2f} mm, maximum {tcia_fit['max_residual_mm']:.2f} mm, {tcia_fit['landmark_count']} landmarks, scale {tcia_fit['scale']:.6f}, volume factor {tcia_fit['volume_scale']:.6f}.",
    f"Pose check over all {tcia_fit['pose_check']['landmark_count']} pelvis, knee and ankle landmarks: RMS {tcia_fit['pose_check']['all_landmark_rms_mm']:.2f} mm, maximum {tcia_fit['pose_check']['all_landmark_max_mm']:.2f} mm (not used). {tcia_fit['pose_check']['interpretation']}", '',
    '| Landmark | Side | Residual mm |', '| --- | --- | ---: |',
    *[f"| {p['landmark']} | {p['side']} | {p['residual_mm']:.2f} |" for p in tcia_fit['landmarks']], '',
    '### Bone-to-bone surface distances, Denver vs transformed TCIA 003', '',
    '| Structure | Denver->TCIA mean mm | p95 mm | Hausdorff mm | Denver inside TCIA envelope (5 mm) | Shape p95 mm after per-bone rigid ICP |',
    '| --- | ---: | ---: | ---: | ---: | ---: |',
    *[row for entry in tcia_fit['surface_distances'] for row in distance_rows(entry)], '',
    'Distances are sampled nearest-neighbour values. In-frame femur, tibia and fibula distances reflect the TCIA 003 lower-limb pose, not a frame error; per-bone rigid ICP compares donor bone shape only.', '',
    *['- ' + limitation for limitation in tcia_fit['limitations']], '',
    '## Acceptance', '',
    *acceptance_rows(),
    f"- manual landmark review: {acceptance['manual_landmark_review']}; anatomical review: {acceptance['anatomical_review']}.", '',
    'All landmarks are automatic geometric rules (`scripts/extract-landmarks.py`) or bounding-box proxies; manual review is pending. Matrices, landmarks and surface distances are in `registration-report.json` and `transforms/`.',
]))

licence = read('generated/licence-report-open-clean.json')
write('generated/licence-report.md', '\n'.join([
    '# Shipped-geometry licence report', '',
    f"Target: {licence['target']}. Mesh references audited: {licence['mesh_references']}. Errors: {len(licence['errors'])}.",
    'HRA, BodyParts3D, TCIA segmentations and Denver VHF models are recorded as CC BY 4.0 with source links and attribution. The NLM VHF CT labels are',
    'derived from public-domain NLM images under the NLM Terms and Conditions (attribution "Courtesy of the U.S. National Library of Medicine") with the',
    'Apache-2.0 TotalSegmentator `total` model; licensed subtasks were not used.',
    'Candidate sources are not approved by this result. Per-asset unknowns remain excluded from the shipped atlases.',
    'This report checks recorded licence compatibility and traceability, not anatomical quality.',
]))

qa = read('generated/qa-report.json')['structures']
anatomy = read('generated/anatomy-qa.json') if exists('generated/anatomy-qa.json') else None
anatomy_index = {(r['atlas'], r['structure']): r for r in anatomy['structures']} if anatomy else {}
rows = []
for atlas in sorted({r['atlas'] for r in qa}):
    subset = [r for r in qa if r['atlas'] == atlas]
    measured = [anatomy_index.get((atlas, r['structure'])) for r in subset]
    measured = [m for m in measured if m]
    rows.append(f"| {atlas} | {len(subset)} | {sum(r['boundary_edges'] > 0 for r in subset)} | {sum(r['nonmanifold_edges'] > 0 for r in subset)} | {sum(r['degenerate_faces'] > 0 for r in subset)} | "
                + (f"{sum(m['self_intersecting_pairs'] > 0 for m in measured)} of {len(measured)} | {sum(bool(m['outlier_components']) for m in measured)} |" if measured else 'not measured | not measured |'))
continuity = anatomy['composite_continuity'] if anatomy else {}
fmt = lambda v: f'{v:.1f}' if isinstance(v, (int, float)) else 'n/a'
write('generated/qa-report.md', '\n'.join([
    '# Geometry QA', '', '| Atlas | Meshes | Open boundaries | Nonmanifold edges | Degenerate triangles | Self-intersecting meshes | Meshes with outlier components |',
    '| --- | ---: | ---: | ---: | ---: | ---: | ---: |', *rows, '',
    'Issue columns count meshes affected. Individual values are in `qa-report.json` and `anatomy-qa.json` (self-intersecting triangle pairs by edge-triangle tests,',
    f"connected components farther than {anatomy['outlier_threshold_mm'] if anatomy else 'n/a'} mm from the main component). Open boundaries can be intentional for anatomical surfaces.",
    *([f"Composite continuity (bounding boxes, canonical stage): HRA head bottom minus CT vertebral column top {fmt(continuity.get('hra_head_bottom_minus_spine_top_mm'))} mm; "
       f"HRA brain inside CT skull box: {continuity.get('hra_brain_inside_ct_skull_box')}; CT vertebral column bottom minus Denver sacrum top {fmt(continuity.get('ct_spine_bottom_minus_denver_sacrum_top_mm'))} mm. {continuity.get('interpretation', '')}"] if anatomy else []),
    'Anatomical review remains pending for every mesh (registry/review-status.json).',
]))

crosswalk = read('registry/ontology-crosswalk-reviewed.json')['summary'] if exists('registry/ontology-crosswalk-reviewed.json') else None
bmf = read('generated/bmftoolkit-comparison.json') if exists('generated/bmftoolkit-comparison.json') else None
write('docs/ONTOLOGY.md', '\n'.join([
    '# Ontology status', '',
    'The catalog is the union of imported terms. HRA and BodyParts3D FMA/UBERON identifiers are kept; `FMA123` is normalized to `FMA:123`.',
    'Dataset-local labels (Denver VHF, TCIA 003, NLM VHF CT) and lateralized FMA identifiers (HRA, BodyParts3D) resolve to UBERON/FMA through',
    '`registry/ontology-crosswalk-reviewed.json`, built by `scripts/build-crosswalk.py` from curated proposals (`registry/crosswalk-proposals.json`)',
    'and the EBI Ontology Lookup Service: every entry stores the OLS record (IRI, label, synonyms, cross-references, definition), the match type',
    '(exact label, exact synonym, FMA parent with UBERON cross-reference) and a review status. Nothing is applied without a retrievable term.', '',
    *([f"Crosswalk summary ({crosswalk['retrieved_at']}): " + '; '.join(f"{s}: {v['applied']} of {v['entries']} applied ({v['uberon']} UBERON, {v['fma_only']} FMA only)" for s, v in crosswalk['by_source'].items()) + '.',
       f"Unresolved or uncertain: {len(crosswalk['unresolved_or_uncertain'])} entries (listed in the file); they keep their source identifiers."] if crosswalk else []), '',
    'Laterality is explicit in canonical keys (`UBERON:0000981|left`). Grouped CT labels (both sides in one mesh) are catalog entries of their own and',
    'appear as `grouped_candidates` (partial coverage) on the lateral entries. Anatomist review of every equivalence is pending; no TA2 mapping has been imported.', '',
    '`source-hierarchy-concept` entries can lack a direct mesh while referencing meshes through their source hierarchy. The coverage report says `no-direct-geometry`,',
    'not that these structures are absent from all anatomical datasets. The catalog must not be advertised as the full human anatomical universe.',
]))
if bmf:
    write('generated/bmftoolkit-comparison.md', '\n'.join([
        '# BMFToolkit versus Denver VHF (same donor, not shipped)', '',
        bmf['licence_evidence']['position'], '',
        '| BMF asset | Geometry | Denver asset | p95 mm | Hausdorff mm | Volume ratio |', '| --- | --- | --- | ---: | ---: | ---: |',
        *[f"| {c['bmf_asset']} | {c['bmf_geometry']} | {c['denver_asset']} | {c['bmf_to_denver']['p95_mm']:.1f} | {c['hausdorff_mm']:.1f} | {c['volume_ratio_bmf_over_denver']:.3f} |" for c in bmf['comparisons']], '',
        f"Median p95: segmented right bones {bmf['summary']['median_p95_mm_segmented_right']:.1f} mm, mirrored left bones {bmf['summary']['median_p95_mm_mirrored_left']:.1f} mm. {bmf['summary']['interpretation']}",
    ]))
print('Wrote dataset, coverage, registration, licence, geometry, ontology and BMFToolkit summaries.')
