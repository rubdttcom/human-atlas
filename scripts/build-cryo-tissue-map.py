"""Versioned tissue-class map for the cryosection pilot: every Denver original label -> one tissue class (plan B stage 2).

Writes registry/cryo-tissue-map.json. The table is explicit and exhaustive (all 131 Denver label values, background
included) so that no label is mapped by a name pattern at training time; the pattern Side_Tissue_Structure of Denver's
names is only used here to propose the class, and the file is what the pipeline reads. Rules fixed in the file:

  classes   0 background (blue block, air, table), 1 bone, 2 cartilage, 3 muscle, 4 ligament-tendon, 5 fat (reserved,
            no Denver source: never assigned in the pilot), 255 ignore
  ignore    inside the body without a Denver label (unknown, never background); every voxel of a slice whose pair status
            is not usable / usable-flagged (excluded-identity, excluded-observability, no Denver reference)
  body      photograph tissue against the blue block, on the resampled Denver-grid RGB: R > B + 25 and max(R, G, B) > 60,
            closing (2 iterations), hole filling, components of at least 811 Denver pixels (3.6 cm2) kept; the same rule
            as scripts/check-photo-ct-alignment.py at 4 px, expressed on the 0.666 mm grid
  order     slice status -> Denver label -> body mask -> background

Denver's 2022 original map has no composite tissue labels (no "fat with fascia", no skin); fat, skin, vessels and nerves
are not labelled and stay ignore inside the body. The two coccyx and two sacrum halves are bone. Denver's spelling of the
names is kept verbatim (Illiacus, QuadratisFemoris, GluetusMinimus, OnturatorInternus, Semitendonosus): they are keys.

  .venv/bin/python scripts/build-cryo-tissue-map.py [--labels data/derived/denver/label-blocks/block2-k2285-3532-labels.npz]

Nothing here is anatomy: it declares which Denver label counts as which tissue for the loss and the metrics.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'registry/cryo-tissue-map.json'
CLASSES = [
    {'value': 0, 'name': 'background', 'definition': 'blue embedding block, air, table: outside the body mask and without a Denver label'},
    {'value': 1, 'name': 'bone', 'definition': 'Denver Bone labels (cortical and trabecular together; Denver does not separate them)'},
    {'value': 2, 'name': 'cartilage', 'definition': 'Denver Cartilage labels (articular cartilage)'},
    {'value': 3, 'name': 'muscle', 'definition': 'Denver Muscle labels (skeletal muscle bellies; tendon is not separated by Denver, so tendinous parts inside a muscle label count as muscle)'},
    {'value': 4, 'name': 'ligament-tendon', 'definition': 'Denver Ligament labels (knee ligaments in this release); tendons have no Denver label'},
    {'value': 5, 'name': 'fat', 'definition': 'reserved; no Denver source in the 2022 release; never assigned in the pilot; reported machine-not-assessable'},
    {'value': 255, 'name': 'ignore', 'definition': 'unknown: inside the body without a Denver label, and every voxel of a slice whose pair status is not usable or usable-flagged; excluded from the loss and from every metric; never background'},
]
TISSUE_TO_CLASS = {'Bone': 1, 'Cartilage': 2, 'Muscle': 3, 'Ligament': 4}
NAME = re.compile(r'^(Left|Right)_(Bone|Cartilage|Ligament|Muscle)_(.+)$')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--labels', default=str(ROOT / 'data/derived/denver/label-blocks/block2-k2285-3532-labels.npz'))
    a = ap.parse_args()
    z = np.load(a.labels, allow_pickle=False)
    meta = json.loads(str(z['meta']))
    names = meta['names']
    present = {int(k): v for k, v in meta['labels_present_in_block'].items()}
    if len(names) != 131 or names[0] != 'Background':
        raise SystemExit('unexpected Denver label list')
    table = []
    for v, nm in enumerate(names):
        if v == 0:
            table.append({'value': 0, 'name': nm, 'class': 0, 'class_name': 'background', 'note': 'Denver 0 is "no label": background only outside the body mask, ignore inside it', 'voxels_block2': present.get(0, 0)})
            continue
        m = NAME.match(nm)
        if not m:
            raise SystemExit(f'Denver name without Side_Tissue_Structure pattern: {nm}')
        cls = TISSUE_TO_CLASS[m.group(2)]
        table.append({'value': v, 'name': nm, 'side': m.group(1), 'denver_tissue': m.group(2), 'structure': m.group(3), 'class': cls,
                      'class_name': next(c['name'] for c in CLASSES if c['value'] == cls), 'voxels_block2': present.get(v, 0)})
    per_class_block2 = {}
    for r in table:
        if r['value'] == 0:
            continue
        per_class_block2[r['class_name']] = per_class_block2.get(r['class_name'], 0) + r['voxels_block2']
    doc = {
        'id': 'cryo-tissue-map', 'version': 1, 'date': '2026-09-13',
        'purpose': 'explicit, exhaustive mapping of every Denver original label value to one tissue class for the loss and the metrics of the cryosection pilot (plan B stage 2); read by scripts/build-cryo-tissue-classes.py; a change is a new version and invalidates any acceptance bound to the old hash',
        'classes': CLASSES,
        'precedence': ['slice pair status not in {usable, usable-flagged} -> every voxel ignore (255)',
                       'Denver label value != 0 -> its class from the table (labels are trusted wherever they are, inside or outside the body mask)',
                       'Denver 0 and body mask true -> ignore (255): unknown tissue, never background',
                       'Denver 0 and body mask false -> background (0)'],
        'body_mask_rule': {'input': 'resampled Denver-grid RGB of the slice (uint8)', 'tissue': 'R > B + 25 and max(R, G, B) > 60',
                           'morphology': 'binary closing 2 iterations, fill holes, keep connected components with at least 811 pixels (3.6 cm2 at 0.666 mm; the 200 blocks of 4 x 4 photograph px of scripts/check-photo-ct-alignment.py)',
                           'note': 'a colour rule against the blue block; frost, dark or block-coloured pixels inside the outline are still body because holes are filled; it decides only background versus unknown, never any tissue'},
        'composite_labels': 'none in Denver 2022 original maps; every non-zero label is one structure of one tissue; fat, skin, fascia, vessels and nerves are unlabelled and stay ignore inside the body',
        'not_supervised_in_pilot': ['fat (class 5, no source)', 'ligament-tendon (class 4) has no voxel in the pelvis block: Denver ligaments are the knee ligaments'],
        'labels': table,
        'per_class_voxels_block2_denver_labels': per_class_block2,
        'sources': {'label_names': 'VHF_Full.mat geometry_labels/name (131 entries, value = index)', 'labels_npz': str(Path(a.labels).relative_to(ROOT)) if str(Path(a.labels).resolve()).startswith(str(ROOT)) else a.labels,
                    'labels_mat_sha256': meta['source_sha256'], 'block2_counts_from': 'labels_present_in_block of the npz (k 2285..3532)'},
        'limits': ['class level only: Denver structures are merged per tissue; a class Dice does not see confusions between neighbouring structures of the same tissue',
                   'Denver does not separate cortical from trabecular bone nor tendon from muscle belly; the classes inherit that',
                   'the body mask is a colour rule and is not anatomy; label voxels never depend on it'],
    }
    OUT.write_text(json.dumps(doc, indent=1))
    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(json.dumps({'done': True, 'out': str(OUT.relative_to(ROOT)), 'labels': len(table), 'per_class_voxels_block2': per_class_block2, 'sha256': sha}))


if __name__ == '__main__':
    main()
