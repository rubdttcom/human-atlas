"""Builder tests, including all retained native voxels of the actual abdominal package."""
import importlib.util
import json
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('builder', ROOT / 'scripts/build-viewer-volume.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test():
    shape = (10, 8, 7)
    x, y, z = np.indices(shape)
    scalar = 13*x + 29*y + 71*z - 1000
    labels = np.where(x < 3, 1, 2).astype('u1')
    support = np.ones(shape, 'u1')
    support[4, 3, 3] = 0  # Not on the stride-3 lattice.
    ct, lab, cover = builder.preview_arrays(scalar, labels, support, 3)
    np.testing.assert_array_equal(ct, scalar[::3, ::3, ::3].transpose(2, 1, 0))
    np.testing.assert_array_equal(lab, labels[::3, ::3, ::3].transpose(2, 1, 0))
    assert cover[1, 1, 1] == 0 and cover[1, 1, 2] == 0
    for oz, oy, ox in np.ndindex(cover.shape):
        at = [ox*3, oy*3, oz*3]
        footprint = tuple(slice(max(0,p-2), min(shape[i],p+3)) for i,p in enumerate(at))
        assert cover[oz,oy,ox] == support[footprint].min()
    for bad in [labels.astype(float)+0.1, labels.astype(float)*float('nan'), labels.astype(float)+256]:
        try:
            builder.preview_arrays(scalar,bad,support,3)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid labels accepted')
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        first = builder.build(out)
        second = builder.build(out)
        assert first['manifestSha256'] == second['manifestSha256'], 'Builder is not reproducible'
        manifest = json.loads((out/'manifest.json').read_text())
        level = manifest['levels'][0]
        shape = tuple(reversed(level['dimensions']))
        for key, file, dtype in [('intensity','vhf-fresh-ct.nii.gz','<f4'),('labels','totalseg.nii','u1')]:
            actual = np.fromfile(out/level['chunks'][key]['url'],dtype=dtype).reshape(shape)
            source = nib.load(ROOT/'data/derived/nlm-vhf'/file)
            expected = np.asarray(source.dataobj[:, :, 408:720])[::3, ::3, ::3].transpose(2,1,0)
            np.testing.assert_array_equal(actual,expected)
        output_affine = np.array(level['voxelToStage']).reshape(4,4)
        source_affine = np.array(json.loads((ROOT/'public/atlases/nlm-vhf-ct.json').read_text())['voxel_to_stage'])
        for p in [[0,0,0],[170,170,103],[85,85,51]]:
            expected = source_affine @ [p[0]*3,p[1]*3,p[2]*3+408,1]
            np.testing.assert_allclose(output_affine @ [*p,1],expected,rtol=0,atol=1e-12)
    print(json.dumps({'ok': True, 'native_ct_and_labels': 'all 3,041,064 retained voxel centres exact',
                      'reproducible': True, 'gap_between_preview_centres': 'refused'}))


if __name__ == '__main__':
    test()
