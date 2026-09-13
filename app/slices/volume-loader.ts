import type { LoadedVolume, VolumeManifest } from './types.ts';
import { inverseAffine } from './coordinates.ts';

const MAX_BYTES = 32 * 1024 * 1024;
const organIds: Record<number, string> = {1:'spleen',2:'kidney_right',3:'kidney_left',5:'liver',6:'stomach',52:'aorta',63:'inferior_vena_cava'};
const sha = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const equal = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
function requireValue(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(`Volume unavailable: ${message}`);
}
function finiteArray(value: unknown, length: number): value is number[] {
  return Array.isArray(value) && value.length === length && value.every(Number.isFinite);
}

/** Refuse unsupported formats and identity ambiguity before allocating any volume buffer. */
export function parseManifest(value: unknown): VolumeManifest {
  requireValue(typeof value === 'object' && value !== null, 'invalid manifest');
  const m = value as VolumeManifest;
  requireValue(m.version === 1 && m.id === 'nlm-vhf-abdomen-preview' && m.source === 'nlm-vhf-ct' && m.donor === 'VHF' && m.modality === 'CT', 'incompatible source');
  requireValue(m.axisOrder === 'zyx-x-fastest' && m.byteOrder === 'little' && m.compression === 'none' && equal(m.channelOrder,['HU']), 'unsupported storage');
  requireValue(m.scalarType === 'float32' && m.labelType === 'uint8' && m.supportType === 'uint8', 'unsupported scalar types');
  requireValue(m.units === 'metres' && m.voxelConvention === 'integer-centres', 'unsupported coordinate convention');
  requireValue(m.intensity?.units === 'HU' && m.intensity.scale === 1 && m.intensity.intercept === 0, 'HU conversion must already be applied');
  requireValue(finiteArray(m.intensity.range,2) && m.intensity.range[0] <= m.intensity.range[1], 'invalid HU range');
  requireValue(m.intensity.window?.width > 0 && Number.isFinite(m.intensity.window.width) && Number.isFinite(m.intensity.window.level), 'invalid window');
  requireValue(m.coverage?.['0'] === 'outside-coverage' && m.coverage['1'] === 'acquired' && m.coverage.missingChunk === 'unavailable' && typeof m.coverage.rule === 'string', 'invalid coverage semantics');
  requireValue(m.attribution === 'Courtesy of the U.S. National Library of Medicine' && typeof m.derivedNotice === 'string' && typeof m.overlayNotice === 'string' && m.licence && Object.keys(m.licence).length, 'missing source details');
  for (const key of ['ct','labels','support','classMap','ctMetadata','registration','stageTransform','atlas'])
    requireValue(sha(m.inputs?.[key]?.sha256) && typeof m.inputs[key].path === 'string', `missing ${key} identity`);
  requireValue(sha(m.builder?.sha256) && m.builder.version === 1, 'missing builder identity');
  requireValue(Array.isArray(m.levels) && m.levels.length === 1, 'expected one preview level');
  const l = m.levels[0];
  requireValue(l && typeof l === 'object', 'invalid preview level');
  requireValue(finiteArray(l.dimensions,3) && l.dimensions.every(d => Number.isInteger(d) && d > 1 && d <= 512), 'invalid dimensions');
  const count = l.dimensions.reduce((a,b) => a*b,1);
  requireValue(l.decodedBytes === count*6 && l.decodedBytes <= MAX_BYTES, 'memory budget exceeded');
  requireValue(finiteArray(l.voxelToStage,16) && finiteArray(l.voxelToSourcePhysical,16), 'missing affines');
  inverseAffine(l.voxelToStage); inverseAffine(l.voxelToSourcePhysical);
  requireValue(equal(l.voxelToStage,l.labelVoxelToStage), 'mask grid differs from CT');
  requireValue(l.sourcePhysicalUnits === 'mm' && finiteArray(l.spacingMm,3) && l.spacingMm.every(s => s > 0), 'invalid physical spacing');
  for (let i=0;i<3;i++) requireValue(Math.abs(Math.hypot(l.voxelToStage[i],l.voxelToStage[i+4],l.voxelToStage[i+8])*1000-l.spacingMm[i]) < 1e-6, 'affine spacing mismatch');
  requireValue(Number.isInteger(l.stride) && l.stride > 0 && Array.isArray(l.cropBounds) && l.cropBounds.length === 3, 'invalid crop');
  l.cropBounds.forEach((b,i) => requireValue(finiteArray(b,2) && b.every(Number.isInteger) && b[0] >= 0 && b[1] > b[0] && Math.ceil((b[1]-b[0])/l.stride) === l.dimensions[i], 'crop dimensions mismatch'));
  requireValue(equal(m.region?.inputBounds,l.cropBounds) && finiteArray(m.region.initialVoxel,3) && m.region.initialVoxel.every((p,i) => p >= 0 && p <= l.dimensions[i]-1), 'invalid initial region');
  for (const key of ['intensity','labels','support'] as const) {
    const chunk = l.chunks?.[key];
    requireValue(chunk && sha(chunk.sha256) && chunk.url === `${key}-${chunk.sha256}.bin` && equal(chunk.dimensions,l.dimensions) && chunk.bytes === count*(key === 'intensity' ? 4 : 1), `invalid ${key} chunk`);
  }
  requireValue(Array.isArray(m.labels) && m.labels.length === 7, 'missing organ mapping');
  const seen = new Set<number>();
  for (const label of m.labels) {
    requireValue(!seen.has(label.value) && label.assetId === `NLMCT:VHF:${organIds[label.value]}` && organIds[label.value], 'wrong label mapping');
    seen.add(label.value);
    requireValue(typeof label.name === 'string' && /^#[a-f0-9]{6}$/i.test(label.color) && sha(label.geometrySha256), 'invalid mesh metadata');
    requireValue(Array.isArray(label.bounds) && label.bounds.length === 2 && label.bounds.every(b => finiteArray(b,3)) && label.bounds[0].every((v,i) => v <= label.bounds[1][i]), 'invalid mesh bounds');
    requireValue(label.provenance?.source === m.source && label.provenance.source_asset === label.assetId, 'incompatible mesh provenance');
    const qa = label.provenance.geometry_qa as {geometry_sha256?: string} | undefined;
    requireValue(qa?.geometry_sha256 === label.geometrySha256, 'mesh geometry identity mismatch');
  }
  return m;
}

export async function sha256(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256',bytes);
  return [...new Uint8Array(digest)].map(v => v.toString(16).padStart(2,'0')).join('');
}

interface SourceAtlas {
  input_sha256: string;
  labels_sha256: string;
  voxel_to_stage: number[][];
  source_affine: number[][];
  parts: {id: string; bounds: number[][]; source_metadata: {label_value: number}; provenance: Record<string, unknown>}[];
}
/** The current source atlas is fetched by fixed URL, independently of manifest URLs. */
export function bindAtlas(manifest: VolumeManifest, atlas: SourceAtlas) {
  requireValue(atlas.input_sha256 === manifest.inputs.ct.sha256 && atlas.labels_sha256 === manifest.inputs.labels.sha256, 'source volume identities differ');
  const l = manifest.levels[0];
  for (const [source,output] of [[atlas.voxel_to_stage,l.voxelToStage],[atlas.source_affine,l.voxelToSourcePhysical]] as const) {
    requireValue(Array.isArray(source) && source.length === 4 && source.every(r => finiteArray(r,4)), 'source affine missing');
    for (let r=0;r<4;r++) for (let c=0;c<4;c++) {
      const expected = c === 3 ? source[r][3]+[0,1,2].reduce((sum,k) => sum+source[r][k]*l.cropBounds[k][0],0) : source[r][c]*l.stride;
      requireValue(Math.abs(output[r*4+c]-expected) <= 1e-9, 'crop/registration affine differs from source meshes');
    }
  }
  for (const label of manifest.labels) {
    const part = atlas.parts.find(p => p.id === label.assetId);
    requireValue(part && part.source_metadata.label_value === label.value && equal(part.bounds,label.bounds) && equal(part.provenance,label.provenance), 'label or mesh provenance differs from current atlas');
  }
}

async function boundedFetch(url: string, limit: number, signal: AbortSignal, fetcher: typeof fetch): Promise<ArrayBuffer> {
  const response = await fetcher(url,{signal});
  requireValue(response.ok, `missing asset (${response.status})`);
  requireValue(response.body, 'empty asset');
  const reader = response.body.getReader();
  const parts: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const {value,done} = await reader.read();
      if (done) break;
      size += value.byteLength;
      requireValue(size <= limit, 'asset exceeds declared size');
      parts.push(value);
    }
  } catch (error) { await reader.cancel(); throw error; }
  finally { reader.releaseLock(); }
  signal.throwIfAborted();
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) { bytes.set(part,offset); offset += part.byteLength; }
  return bytes.buffer;
}

/** No global cache: workspace owns exactly one package; abort + generation rejects late responses. */
export class VolumeLoader {
  private generation = 0;
  private controller?: AbortController;
  cancel() { this.generation++; this.controller?.abort(); this.controller = undefined; }
  async load(url: string, fetcher: typeof fetch = fetch): Promise<LoadedVolume> {
    this.cancel();
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    const signal = controller.signal;
    try {
      const raw = await boundedFetch(url,1024*1024,signal,fetcher);
      const manifest = parseManifest(JSON.parse(new TextDecoder().decode(raw)));
      const atlasBytes = await boundedFetch(new URL('/atlases/nlm-vhf-ct.json',url).href,2*1024*1024,signal,fetcher);
      requireValue(await sha256(atlasBytes) === manifest.inputs.atlas.sha256, 'source atlas changed; rebuild the preview');
      bindAtlas(manifest,JSON.parse(new TextDecoder().decode(atlasBytes)));
      const level = manifest.levels[0];
      const buffers: ArrayBuffer[] = [];
      // Sequential chunks cap decoding transient memory; network/decoded package is ~17.4 MiB.
      for (const key of ['intensity','labels','support'] as const) {
        const chunk = level.chunks[key];
        const bytes = await boundedFetch(new URL(chunk.url,url).href,chunk.bytes,signal,fetcher);
        requireValue(bytes.byteLength === chunk.bytes && await sha256(bytes) === chunk.sha256, `${key} integrity failure`);
        signal.throwIfAborted();
        buffers.push(bytes);
      }
      requireValue(generation === this.generation, 'stale package response');
      const intensity = new Float32Array(buffers[0]);
      // Explicit disk byte order also supports hypothetical big-endian clients.
      if (new Uint8Array(new Uint32Array([1]).buffer)[0] !== 1) {
        const data = new DataView(buffers[0]);
        for (let i=0;i<intensity.length;i++) intensity[i] = data.getFloat32(i*4,true);
      }
      requireValue(intensity.every(v => Number.isFinite(v) && v >= manifest.intensity.range[0] && v <= manifest.intensity.range[1]), 'invalid HU values');
      const support = new Uint8Array(buffers[2]);
      requireValue(support.every(v => v === 0 || v === 1), 'invalid support values');
      return {manifest,dimensions:level.dimensions,voxelToStage:level.voxelToStage,stageToVoxel:inverseAffine(level.voxelToStage),intensity,labels:new Uint8Array(buffers[1]),support};
    } catch (error) { controller.abort(); throw error; }
    finally { if (this.controller === controller) this.controller = undefined; }
  }
}
