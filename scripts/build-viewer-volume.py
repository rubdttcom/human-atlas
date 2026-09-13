"""Read-only NLM abdominal preview derivative. Never changes source data or registries.

Usage: .venv/bin/python scripts/build-viewer-volume.py [--serve]
Outputs ignored data/derived/viewer/nlm-abdomen; --serve also copies to public/volumes/nlm-abdomen.
"""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.ndimage import minimum_filter

ROOT = Path(__file__).resolve().parents[1]
ORGANS = {1: 'spleen', 2: 'kidney_right', 3: 'kidney_left', 5: 'liver',
          6: 'stomach', 52: 'aorta', 63: 'inferior_vena_cava'}
COLORS = ['#bb72b5', '#db9862', '#d8b06c', '#b96258', '#d7a783', '#e45e65', '#658ad2']


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def preview_arrays(ct, labels, support, stride):
    """Inputs are already cropped, xyz. Preserve intervening holes, not just sampled support.

    A supported output centre requires every input voxel within stride-1 along
    each axis. Thus any unsupported input between adjacent output centres vetoes
    interpolation in that cell. Crop boundaries extend the edge (no invented data).
    """
    if ct.shape != labels.shape or ct.shape != support.shape:
        raise ValueError('CT, labels and coverage shapes differ')
    if not np.isfinite(ct).all() or not np.isfinite(labels).all():
        raise ValueError('Non-finite source value')
    if not np.isin(support, [0, 1]).all():
        raise ValueError('Coverage must be binary')
    if (labels < 0).any() or (labels > 255).any() or not np.equal(labels, np.floor(labels)).all():
        raise ValueError('Labels must be integral uint8 values')
    steps = (slice(None, None, stride),) * 3
    conservative = minimum_filter(support, size=2 * stride - 1, mode='nearest')
    return [np.ascontiguousarray(a[steps].transpose(2, 1, 0), dtype=dtype)
            for a, dtype in [(ct, '<f4'), (labels, 'u1'), (conservative, 'u1')]]


def build(out, serve=False):
    started = time.monotonic()
    source = ROOT / 'data/derived/nlm-vhf'
    files = {'ct': source / 'vhf-fresh-ct.nii.gz', 'labels': source / 'totalseg.nii',
             'support': source / 'ct-coverage-mask.nii.gz', 'classMap': source / 'totalseg-classmap.json',
             'ctMetadata': source / 'vhf-fresh-ct-metadata.json',
             'registration': ROOT / 'transforms/nlm-ct-to-vhf.json',
             'stageTransform': ROOT / 'transforms/source-to-stage.json',
             'atlas': ROOT / 'public/atlases/nlm-vhf-ct.json'}
    identities = {key: {'path': str(path.relative_to(ROOT)), 'sha256': digest(path)} for key, path in files.items()}
    atlas, registration, stage, meta = [read_json(files[k]) for k in ['atlas', 'registration', 'stageTransform', 'ctMetadata']]
    if identities['ct']['sha256'] != atlas['input_sha256'] or identities['ct']['sha256'] != meta['sha256']:
        raise ValueError('CT identity differs from the mesh source')
    if identities['labels']['sha256'] != atlas['labels_sha256'] or identities['labels']['sha256'] != registration['labels_sha256']:
        raise ValueError('Label identity differs from mesh/registration source')
    images = [nib.load(files[k]) for k in ['ct', 'labels', 'support']]
    image = images[0]
    for other in images[1:]:
        if other.shape != image.shape or not np.allclose(other.affine, image.affine, atol=1e-9, rtol=0):
            raise ValueError('Input grids differ')
    if image.shape != (512, 512, 1734) or not np.allclose(image.affine, atlas['source_affine'], atol=1e-9, rtol=0):
        raise ValueError('Unexpected acquisition grid')
    crop = [[0, 512], [0, 512], [408, 720]]
    stride = 3
    selection = tuple(slice(lo, hi) for lo, hi in crop)
    arrays = preview_arrays(*(np.asanyarray(v.dataobj[selection]) for v in images), stride)
    output_to_input = np.diag([stride, stride, stride, 1.0])
    output_to_input[:3, 3] = [a[0] for a in crop]
    voxel_to_source = image.affine @ output_to_input
    source_to_stage = (np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4)
                       @ np.array(registration['matrix_row_major']).reshape(4, 4))
    if not np.allclose(source_to_stage @ image.affine, atlas['voxel_to_stage'], atol=1e-9, rtol=0):
        raise ValueError('Mesh and volume stage transforms differ')
    class_map = read_json(files['classMap'])['total']
    mappings = []
    for (value, label), color in zip(ORGANS.items(), COLORS):
        asset = 'NLMCT:VHF:' + label
        part = next(p for p in atlas['parts'] if p['id'] == asset)
        provenance = part['provenance']
        if class_map[str(value)] != label or part['source_metadata']['label_value'] != value:
            raise ValueError('Label to asset mapping differs')
        chunk_path = ROOT / 'public' / atlas['chunks'][part['chunk']]['url'].lstrip('/')
        blob = chunk_path.read_bytes()
        geometry = hashlib.sha256(blob[part['positions']:part['positions'] + part['vertexCount'] * 12]
                                  + blob[part['indices']:part['indices'] + part['indexCount'] * 4]).hexdigest()
        if geometry != provenance['geometry_qa']['geometry_sha256']:
            raise ValueError('Mesh geometry identity differs')
        mappings.append({'value': value, 'assetId': asset, 'name': part['name'], 'color': color,
                         'geometrySha256': geometry, 'bounds': part['bounds'], 'provenance': provenance})
    dimensions = list(reversed(arrays[0].shape))
    if sum(a.nbytes for a in arrays) > 32 * 1024**2:
        raise ValueError('Preview exceeds frozen package budget')
    out.mkdir(parents=True, exist_ok=True)
    chunks = {}
    for key, array in zip(['intensity', 'labels', 'support'], arrays):
        content = array.tobytes()
        sha = hashlib.sha256(content).hexdigest()
        # Content-addressed files make replacing the manifest safe for active clients.
        name = f'{key}-{sha}.bin'
        (out / name).write_bytes(content)
        chunks[key] = {'url': name, 'sha256': sha, 'bytes': len(content), 'dimensions': dimensions}
    manifest = {
        'version': 1, 'id': 'nlm-vhf-abdomen-preview', 'source': 'nlm-vhf-ct', 'donor': 'VHF', 'modality': 'CT',
        'builder': {'path': 'scripts/build-viewer-volume.py', 'sha256': digest(__file__), 'version': 1},
        'inputs': identities, 'attribution': 'Courtesy of the U.S. National Library of Medicine',
        'licence': atlas['licence_evidence'], 'derivedNotice': 'Display derivative; not the current NLM data. Anatomy unreviewed.',
        'axisOrder': 'zyx-x-fastest', 'byteOrder': 'little', 'compression': 'none', 'channelOrder': ['HU'],
        'scalarType': 'float32', 'labelType': 'uint8', 'supportType': 'uint8',
        'units': 'metres', 'voxelConvention': 'integer-centres',
        'intensity': {'units': 'HU', 'scale': 1, 'intercept': 0,
                      'range': [float(arrays[0].min()), float(arrays[0].max())], 'window': {'width': 400, 'level': 50}},
        'coverage': {'0': 'outside-coverage', '1': 'acquired', 'missingChunk': 'unavailable',
                     'rule': 'minimum over stride-1 input neighbours on every axis; all nonzero interpolation weights need support',
                     'sourceLimit': 'Existing coverage excludes <= -999 HU padding/air at full field; conservative support, not a tissue mask.'},
        'region': {'inputBounds': crop, 'initialVoxel': [(d - 1) / 2 for d in dimensions]},
        'labels': mappings, 'unmappedLabels': 'No selectable overlay; original value preserved',
        'overlayNotice': 'Original model masks; component removal, smoothing and decimation can make meshes differ.',
        'levels': [{'id': 'preview', 'dimensions': dimensions, 'spacingMm': [2.8125, 2.8125, 3],
                    'stride': stride, 'cropBounds': crop, 'voxelToSourcePhysical': voxel_to_source.ravel().tolist(),
                    'sourcePhysicalUnits': 'mm', 'voxelToStage': (source_to_stage @ voxel_to_source).ravel().tolist(),
                    'labelVoxelToStage': (source_to_stage @ voxel_to_source).ravel().tolist(),
                    'decodedBytes': sum(a.nbytes for a in arrays), 'chunks': chunks}],
    }
    text = json.dumps(manifest, indent=2) + '\n'
    temporary = out / 'manifest.json.tmp'
    temporary.write_text(text)
    temporary.replace(out / 'manifest.json')
    if serve:
        destination = ROOT / 'public/volumes/nlm-abdomen'
        destination.mkdir(parents=True, exist_ok=True)
        for chunk in chunks.values():
            shutil.copyfile(out / chunk['url'], destination / chunk['url'])
        temporary = destination / 'manifest.json.tmp'
        temporary.write_text(text)
        temporary.replace(destination / 'manifest.json')
    return {'ok': True, 'out': str(out), 'dimensions': dimensions, 'decodedBytes': manifest['levels'][0]['decodedBytes'],
            'seconds': round(time.monotonic() - started, 3), 'manifestSha256': digest(out / 'manifest.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(ROOT / 'data/derived/viewer/nlm-abdomen', args.serve)), flush=True)
