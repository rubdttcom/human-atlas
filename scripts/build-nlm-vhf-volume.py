"""Assemble the NLM Visible Human Female fresh CT into one whole-body NIfTI with header evidence.

Input : data/raw/nlm-vhf/normalCT/c_vf????.fre.Z (GE Genesis 16-bit, 3416-byte header, Unix compress)
        data/raw/nlm-vhf/normalCTHeaders/c_vf????.txt (GE header dumps: pixel size, location, centre)
Output: data/derived/nlm-vhf/vhf-fresh-ct.nii.gz (RAS, millimetres) and vhf-fresh-ct-metadata.json.

Facts read from the headers (recorded in the metadata file):
- 1734 axial slices, 512x512, 1 mm slice spacing, numbered c_vf1001 (vertex) to c_vf2734 (feet).
- Two exams the same day (GE exam 370: files 1001-1985; exam 371: files 1986-2734). The table position
  was re-zeroed between exams, so the header S coordinate is continuous only inside an exam.
- Display field of view changes between body segments (250, 370, 440, 480 mm), so pixel size changes.

Reconstruction rule (no manual alignment):
- z: one slice per millimetre in file order, z_RAS = -(file_number - 1001) mm, i.e. the vertex slice is
  z = 0 and z decreases towards the feet. Inside each exam this equals the header S coordinate up to a
  constant; the exam junction is assumed continuous (1 mm) and its in-plane consistency is measured by
  cross-correlating the two adjacent slices (reported, not corrected).
- x, y: every slice is resampled (linear) onto a common 480 mm field of view, 512 x 512, 0.9375 mm,
  centred at the header plane centre (R, A), with GE row/column directions (columns to patient left,
  rows to posterior). Pixels outside a smaller field of view are air (-1000 HU).
- Intensity: Hounsfield units = stored value - offset, offset measured from air in the image corners.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path
import numpy as np
import nibabel as nib
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/nlm-vhf'
OUT = ROOT / 'data/derived/nlm-vhf'
OUT.mkdir(parents=True, exist_ok=True)
HEADER_BYTES = 3416
GRID = 512
FOV = 480.0
PIXEL = FOV / GRID
FIELDS = {'exam': 'Suite ID for this series', 'series': 'Series number for this image', 'image_number': 'Image Number', 'thickness_mm': 'Slice Thickness (mm)',
          'pixel_x_mm': 'Image pixel size - X', 'pixel_y_mm': 'Image pixel size - Y', 'fov_mm': 'Display Field of view - X (mm)',
          'centre_r': 'Center R coord of plane image', 'centre_a': 'Center A coord of plane image', 'centre_s': 'Center S coord of Plane image',
          'spacing_mm': 'Spacing Between scans(mm)', 'matrix_x': 'Image matrix size - X', 'matrix_y': 'Image matrix size - Y',
          'table_height': 'Table Heigth', 'patient_position': 'Patient Position', 'series_description': 'Series Description', 'text': 'Text'}
manifest = {r['local'].split('/')[-1]: r for r in json.loads((RAW / 'download-manifest.json').read_text())}


def parse_header(path):
    text = path.read_text(errors='replace')
    values = {}
    for key, label in FIELDS.items():
        match = re.search(r'^' + re.escape(label) + r'\.*:\s*(.*)$', text, re.M)
        values[key] = match.group(1).strip() if match else None
    for key in ('thickness_mm', 'pixel_x_mm', 'pixel_y_mm', 'fov_mm', 'centre_r', 'centre_a', 'centre_s', 'spacing_mm', 'table_height'):
        values[key] = float(values[key].split()[0]) if values[key] else None
    for key in ('series', 'image_number', 'matrix_x', 'matrix_y'):
        values[key] = int(values[key].split()[0])
    exam = re.search(r'Recon \w+/(\d+)/', values['text'] or '')
    values['exam'] = int(exam.group(1)) if exam else None
    return values


def read_slice(path):
    raw = subprocess.run(['gzip', '-dc', str(path)], check=True, capture_output=True).stdout
    header = parse_header(RAW / 'normalCTHeaders' / (path.name.replace('.fre.Z', '.txt')))
    expected = HEADER_BYTES + header['matrix_x'] * header['matrix_y'] * 2
    assert len(raw) == expected, (path.name, len(raw), expected)
    pixels = np.frombuffer(raw, dtype='>i2', offset=HEADER_BYTES).reshape(header['matrix_y'], header['matrix_x']).astype(np.float32)
    return header, pixels


files = sorted((RAW / 'normalCT').glob('c_vf*.fre.Z'))
numbers = [int(f.name[4:8]) for f in files]
assert numbers == list(range(1001, 1001 + len(files))), 'slice numbering must be contiguous'
volume = np.full((GRID, GRID, len(files)), -1000, dtype=np.int16)   # (col -> x, row -> y, slice)
headers, segments, offsets = [], [], []
grid_cols = (np.arange(GRID) - (GRID - 1) / 2) * PIXEL   # mm from plane centre, +towards patient left
grid_rows = (np.arange(GRID) - (GRID - 1) / 2) * PIXEL   # mm from plane centre, +towards posterior
for index, path in enumerate(files):
    header, pixels = read_slice(path)
    header['file'] = path.name
    header['sha256'] = manifest[path.name]['sha256']
    corners = np.concatenate([pixels[:32, :32].ravel(), pixels[:32, -32:].ravel(), pixels[-32:, :32].ravel(), pixels[-32:, -32:].ravel()])
    offset = float(np.median(corners)) + 1000.0
    offsets.append(offset)
    hu = pixels - offset
    # Source pixel coordinates of every target grid point (same plane centre, different pixel size).
    src_cols = grid_cols / header['pixel_x_mm'] + (header['matrix_x'] - 1) / 2
    src_rows = grid_rows / header['pixel_y_mm'] + (header['matrix_y'] - 1) / 2
    rows, cols = np.meshgrid(src_rows, src_cols, indexing='ij')
    resampled = ndimage.map_coordinates(hu, [rows, cols], order=1, mode='constant', cval=-1000.0)
    volume[:, :, index] = np.clip(np.round(resampled.T), -1024, 3071).astype(np.int16)
    headers.append(header)
    key = (header['exam'], header['fov_mm'], header['centre_r'], header['centre_a'])
    if not segments or segments[-1]['key'] != key or abs(header['centre_s'] - segments[-1]['last_s'] + 1) > 0.01:
        segments.append({'key': key, 'exam': header['exam'], 'fov_mm': header['fov_mm'], 'pixel_mm': header['pixel_x_mm'], 'centre_r': header['centre_r'],
                         'centre_a': header['centre_a'], 'first_file': path.name, 'first_index': index, 'first_s': header['centre_s'],
                         'table_height': header['table_height'], 'header_text': header['text']})
    segments[-1].update({'last_file': path.name, 'last_index': index, 'last_s': header['centre_s'], 'slices': index - segments[-1]['first_index'] + 1})
    if index % 200 == 0:
        print(f'{index}/{len(files)} slices', flush=True)
for segment in segments:
    del segment['key']
assert all(h['spacing_mm'] == 1.0 and h['thickness_mm'] == 1.0 and h['patient_position'].endswith('Supine') for h in headers)

# Exam junction: in-plane shift between the last slice of exam 370 and the first of exam 371, by phase correlation of soft-tissue masks.
junction = next(i for i in range(1, len(headers)) if headers[i]['exam'] != headers[i - 1]['exam'])
a, b = (volume[:, :, junction - 1] > -300).astype(float), (volume[:, :, junction] > -300).astype(float)
correlation = np.fft.ifft2(np.fft.fft2(a) * np.conj(np.fft.fft2(b)))
peak = np.unravel_index(np.argmax(np.abs(correlation)), correlation.shape)
shift = [((p + GRID // 2) % GRID - GRID // 2) * PIXEL for p in peak]
overlap = float((a * b).sum() / max(1.0, np.maximum(a, b).sum()))

affine = np.array([[-PIXEL, 0, 0, headers[0]['centre_r'] + PIXEL * (GRID - 1) / 2],
                   [0, -PIXEL, 0, headers[0]['centre_a'] + PIXEL * (GRID - 1) / 2],
                   [0, 0, -1.0, 0.0],
                   [0, 0, 0, 1]])
image = nib.Nifti1Image(volume, affine)
image.header.set_xyzt_units('mm')
image.header['descrip'] = b'NLM Visible Human Female fresh CT, header-derived RAS grid'
target = OUT / 'vhf-fresh-ct.nii.gz'
nib.save(image, target)
metadata = {'source': 'NLM Visible Human Female, Female-Images/radiological/normalCT (fresh CT before freezing, GE CT, 22 September 1993 per headers)',
            'terms': 'https://www.nlm.nih.gov/databases/download/terms_and_conditions.html; attribution "Courtesy of the U.S. National Library of Medicine"',
            'file': str(target.relative_to(ROOT)), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'shape': list(volume.shape), 'voxel_mm': [PIXEL, PIXEL, 1.0], 'affine_ras': affine.tolist(),
            'frame': 'RAS millimetres: +x patient right, +y anterior, +z superior; origin at the vertex slice plane centre (header R/A centre)',
            'z_rule': 'z = -(file_number - 1001) mm; header S is continuous only within an exam (table re-zeroed between exams 370 and 371)',
            'exam_junction': {'between_files': [headers[junction - 1]['file'], headers[junction]['file']], 'exams': [headers[junction - 1]['exam'], headers[junction]['exam']],
                              'header_s_mm': [headers[junction - 1]['centre_s'], headers[junction]['centre_s']],
                              'table_height': [headers[junction - 1]['table_height'], headers[junction]['table_height']],
                              'soft_tissue_mask_shift_mm_xy': shift, 'soft_tissue_mask_overlap_iou': overlap,
                              'assumption': 'continuous 1 mm spacing across the junction; no in-plane correction applied'},
            'segments': segments, 'hu_offset_range': [min(offsets), max(offsets)],
            'in_plane_resampling': f'linear onto {FOV:.0f} mm field of view, {GRID}x{GRID}, {PIXEL:.4f} mm; smaller fields of view padded with -1000 HU',
            'slice_sha256': {h['file']: h['sha256'] for h in headers}, 'header_files': [h['file'].replace('.fre.Z', '.txt') for h in headers],
            'note_readme': 'The normalCT README text names the male set (copy error in the source); file names c_vf* and headers identify the female.'}
(OUT / 'vhf-fresh-ct-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps({'file': metadata['file'], 'shape': metadata['shape'], 'segments': [(s['exam'], s['fov_mm'], s['first_file'], s['last_file'], s['slices']) for s in segments],
                  'junction_shift_mm': shift, 'junction_overlap_iou': overlap, 'hu_offset_range': metadata['hu_offset_range']}, indent=1))
