import type { Mat4, Plane, Vec3, View } from './types.ts';

export const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const scale = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a: Vec3, b: Vec3): Vec3 => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
export function unit(a: Vec3): Vec3 {
  const length = Math.hypot(...a);
  if (!Number.isFinite(length) || length < 1e-12) throw new Error('Degenerate direction');
  return scale(a, 1 / length);
}
export function transform(m: Mat4, p: Vec3): Vec3 {
  return [0, 1, 2].map(r => m[r*4]*p[0] + m[r*4+1]*p[1] + m[r*4+2]*p[2] + m[r*4+3]) as Vec3;
}
export function inverseAffine(m: Mat4): Mat4 {
  if (m.length !== 16 || !m.every(Number.isFinite) || m[12] !== 0 || m[13] !== 0 || m[14] !== 0 || m[15] !== 1)
    throw new Error('Expected a finite row-major affine');
  const a: Vec3 = [m[0],m[4],m[8]], b: Vec3 = [m[1],m[5],m[9]], c: Vec3 = [m[2],m[6],m[10]];
  const determinant = dot(a, cross(b,c));
  if (Math.abs(determinant) < 1e-18) throw new Error('Singular affine');
  const rows = [cross(b,c), cross(c,a), cross(a,b)].map(v => scale(v,1/determinant));
  const t: Vec3 = [m[3],m[7],m[11]];
  return [...rows.flatMap(r => [...r, -dot(r,t)]),0,0,0,1];
}

/** NLM acquisition indices: i left, j posterior, k inferior. No stage-axis assumption. */
export function orthogonalPlane(m: Mat4, origin: Vec3, view: View): Plane {
  inverseAffine(m);
  const axes = [0,1,2].map(c => unit([m[c],m[c+4],m[c+8]]));
  if (Math.max(Math.abs(dot(axes[0],axes[1])),Math.abs(dot(axes[0],axes[2])),Math.abs(dot(axes[1],axes[2]))) > 1e-6)
    throw new Error('Sheared acquisition grid is unsupported');
  const right = view === 'sagittal' ? axes[1] : axes[0];
  const up = scale(view === 'axial' ? axes[1] : axes[2], -1);
  return {origin: [...origin], right, up, normal: unit(cross(right,up))};
}

function rotate(v: Vec3, axis: Vec3, degrees: number): Vec3 {
  if (!Number.isFinite(degrees)) throw new Error('Non-finite angle');
  const angle = degrees * Math.PI / 180, c = Math.cos(angle), s = Math.sin(angle);
  return add(add(scale(v,c),scale(cross(axis,v),s)),scale(axis,dot(axis,v)*(1-c)));
}
/** Extrinsic rotations: first initial right axis, then initial up axis; pivot never moves. */
export function obliquePlane(axial: Plane, rightDegrees: number, upDegrees: number): Plane {
  const turn = (v: Vec3) => rotate(rotate(v,axial.right,rightDegrees),axial.up,upDegrees);
  return {origin: [...axial.origin],right: turn(axial.right),up: turn(axial.up),normal: turn(axial.normal)};
}
export const planePoint = (p: Plane, u: number, v: number): Vec3 => add(p.origin,add(scale(p.right,u),scale(p.up,v)));
export const translatePlane = (p: Plane, metres: number): Plane => ({...p,origin:add(p.origin,scale(p.normal,metres))});
/** Canvas y points down. Extent is in metres, and samples are at pixel centres. */
export function pixelPoint(p: Plane, x: number, y: number, width: number, height: number, metresPerPixel: number): Vec3 {
  return planePoint(p,(x+.5-width/2)*metresPerPixel,(height/2-y-.5)*metresPerPixel);
}
export function projectPoint(p: Plane, point: Vec3): Vec3 {
  const delta = add(point,scale(p.origin,-1));
  return [dot(delta,p.right),dot(delta,p.up),dot(delta,p.normal)];
}
/** Actual canonical anatomical direction, largest component first; mixed labels above 0.2. */
export function directionLabel(direction: Vec3): string {
  const v = unit(direction);
  return v.map((value,axis) => ({value,axis})).filter(r => Math.abs(r.value) >= .2)
    .sort((a,b) => Math.abs(b.value)-Math.abs(a.value))
    .map(({value,axis}) => (value >= 0 ? ['L','S','A'] : ['R','I','P'])[axis]).join('');
}
