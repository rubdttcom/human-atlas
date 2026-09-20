import type { Sample, Vec3, VolumeGrid } from './types.ts';
import { transform } from './coordinates.ts';

/** Reference trilinear HU + nearest categorical label. Any contributing unsupported voxel vetoes HU. */
export function sampleVoxel(volume: VolumeGrid, point: Vec3): Sample {
  const {dimensions: d, intensity, labels, support} = volume;
  if (!point.every(Number.isFinite)) return {state:'unavailable'};
  // Permit floating point round-trip noise at the outermost voxel centre only.
  if (point.some((v,i) => v < -1e-7 || v > d[i]-1+1e-7)) return {state:'outside-coverage'};
  const p = point.map((v,i) => Math.max(0,Math.min(d[i]-1,v))) as Vec3;
  const low = p.map(Math.floor), high = low.map((v,i) => Math.min(d[i]-1,v+1));
  const fraction = p.map((v,i) => v-low[i]);
  const index = (x: number,y: number,z: number) => x+d[0]*(y+d[1]*z);
  let hu = 0;
  for (let z=0;z<2;z++) for (let y=0;y<2;y++) for (let x=0;x<2;x++) {
    const bits = [x,y,z];
    const weight = bits.reduce((w,b,i) => w*(b ? fraction[i] : 1-fraction[i]),1);
    if (weight === 0) continue;
    const at = index(x ? high[0] : low[0],y ? high[1] : low[1],z ? high[2] : low[2]);
    if (support[at] === undefined || intensity[at] === undefined) return {state:'unavailable'};
    if (support[at] !== 1) return {state:'outside-coverage'};
    if (!Number.isFinite(intensity[at])) return {state:'unavailable'};
    hu += weight*intensity[at];
  }
  const label = labels[index(...p.map(Math.round) as Vec3)];
  return label === undefined ? {state:'unavailable'} : {state:'acquired',hu,label};
}
export const sampleStage = (volume: VolumeGrid, point: Vec3): Sample => {
  // Affine inversion can turn an exact centre into e.g. 50.99999999999994.
  // Remove double-precision round-off before constructing the interpolation footprint.
  // sampleVoxel itself continues to require support for every genuinely nonzero weight.
  const voxel=transform(volume.stageToVoxel,point).map(v=>Math.abs(v-Math.round(v))<1e-10?Math.round(v):v) as Vec3;
  return sampleVoxel(volume,voxel);
};
export function windowValue(hu: number, width: number, level: number): number {
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(level)) throw new Error('Window width must be positive and level finite');
  return Math.max(0,Math.min(1,(hu-level)/width+.5));
}
