/** Stage coordinates are metres; integer voxel indices denote voxel centres. */
export type Vec3 = [number, number, number];
export type Mat4 = number[]; // row-major, affine, length 16
export type View = 'axial' | 'coronal' | 'sagittal';
export interface Plane {
  origin: Vec3;
  right: Vec3;
  up: Vec3;
  normal: Vec3;
}
export interface VolumeGrid {
  dimensions: Vec3;
  voxelToStage: Mat4;
  stageToVoxel: Mat4;
  /** x fastest: x + nx * (y + ny * z), little endian on disk. */
  intensity: Float32Array;
  labels: Uint8Array;
  /** 0 outside acquired coverage, 1 acquired; missing chunks never become zero. */
  support: Uint8Array;
}
export type Sample = { state: 'acquired'; hu: number; label: number }
  | { state: 'outside-coverage' | 'unavailable' };

export interface SliceLabel {
  value: number;
  assetId: string;
  name: string;
  color: string;
  geometrySha256: string;
  bounds: [Vec3, Vec3];
  provenance: Record<string, unknown>;
}
export interface VolumeChunk {
  url: string;
  sha256: string;
  bytes: number;
  dimensions: Vec3;
}
export interface VolumeLevel {
  id: string;
  dimensions: Vec3;
  spacingMm: Vec3;
  stride: number;
  cropBounds: [number, number][];
  voxelToSourcePhysical: Mat4;
  sourcePhysicalUnits: 'mm';
  voxelToStage: Mat4;
  labelVoxelToStage: Mat4;
  decodedBytes: number;
  chunks: Record<'intensity' | 'labels' | 'support', VolumeChunk>;
}
export interface VolumeManifest {
  version: 1;
  id: string;
  source: 'nlm-vhf-ct';
  donor: 'VHF';
  modality: 'CT';
  inputs: Record<string, {path: string; sha256: string}>;
  builder: {path: string; sha256: string; version: number};
  attribution: string;
  licence: Record<string, string>;
  derivedNotice: string;
  overlayNotice: string;
  axisOrder: 'zyx-x-fastest';
  byteOrder: 'little';
  compression: 'none';
  channelOrder: ['HU'];
  scalarType: 'float32';
  labelType: 'uint8';
  supportType: 'uint8';
  units: 'metres';
  voxelConvention: 'integer-centres';
  intensity: {units: 'HU'; scale: 1; intercept: 0; range: [number, number]; window: {width: number; level: number}};
  coverage: {'0': 'outside-coverage'; '1': 'acquired'; missingChunk: 'unavailable'; rule: string; sourceLimit: string};
  region: {inputBounds: [number, number][]; initialVoxel: Vec3};
  labels: SliceLabel[];
  levels: [VolumeLevel];
}
export interface LoadedVolume extends VolumeGrid { manifest: VolumeManifest }

export interface SliceFrame {plane: Plane; canvas: HTMLCanvasElement; widthMetres: number; heightMetres: number; revision: number}
export interface SliceSceneConfig {frames: Map<string,SliceFrame>; visible: boolean; center: Vec3; colors: Record<string,string>}
