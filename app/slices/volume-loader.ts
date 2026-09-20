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

const SHA256_K = new Uint32Array([
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
 ]);
const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n));
function sha256Fallback(bytes: ArrayBuffer): string {
  const input = new Uint8Array(bytes), bitLength = input.length * 8;
  const size = ((input.length + 9 + 63) >> 6) << 6, padded = new Uint8Array(size);
  padded.set(input); padded[input.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(size - 8, Math.floor(bitLength / 0x100000000), false);
  view.setUint32(size - 4, bitLength >>> 0, false);
  let h0=0x6a09e667,h1=0xbb67ae85,h2=0x3c6ef372,h3=0xa54ff53a,h4=0x510e527f,h5=0x9b05688c,h6=0x1f83d9ab,h7=0x5be0cd19;
  const w = new Uint32Array(64);
  for (let offset=0;offset<size;offset+=64) {
    for (let i=0;i<16;i++) w[i]=view.getUint32(offset+i*4,false);
    for (let i=16;i<64;i++) {
      const a=rotr(w[i-15],7)^rotr(w[i-15],18)^(w[i-15]>>>3), b=rotr(w[i-2],17)^rotr(w[i-2],19)^(w[i-2]>>>10);
      w[i]=(w[i-16]+a+w[i-7]+b)>>>0;
    }
    let a=h0,b=h1,c=h2,d=h3,e=h4,f=h5,g=h6,hh=h7;
    for (let i=0;i<64;i++) {
      const S1=rotr(e,6)^rotr(e,11)^rotr(e,25), ch=(e&f)^(~e&g), t1=(hh+S1+ch+SHA256_K[i]+w[i])>>>0;
      const S0=rotr(a,2)^rotr(a,13)^rotr(a,22), maj=(a&b)^(a&c)^(b&c), t2=(S0+maj)>>>0;
      hh=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
    }
    h0=(h0+a)>>>0;h1=(h1+b)>>>0;h2=(h2+c)>>>0;h3=(h3+d)>>>0;h4=(h4+e)>>>0;h5=(h5+f)>>>0;h6=(h6+g)>>>0;h7=(h7+hh)>>>0;
  }
  return [h0,h1,h2,h3,h4,h5,h6,h7].map(v=>v.toString(16).padStart(8,'0')).join('');
}
export async function sha256(bytes: ArrayBuffer): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (subtle) {
    const digest = await subtle.digest('SHA-256',bytes);
    return [...new Uint8Array(digest)].map(v => v.toString(16).padStart(2,'0')).join('');
  }
  // HTTP LAN previews do not expose SubtleCrypto; retain the same integrity check
  // with a small standards-based fallback rather than failing before the first slice.
  return sha256Fallback(bytes);
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
