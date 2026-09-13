import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {parseManifest,bindAtlas,VolumeLoader} from '../app/slices/volume-loader.ts';
const root=resolve(new URL('..',import.meta.url).pathname);
const directory=resolve(root,'public/volumes/nlm-abdomen');
const original=JSON.parse(await readFile(resolve(directory,'manifest.json'),'utf8'));
const atlas=JSON.parse(await readFile(resolve(root,'public/atlases/nlm-vhf-ct.json'),'utf8'));
parseManifest(original);bindAtlas(original,atlas);
const clone=()=>structuredClone(original);
let refused=0;
for(const mutate of [
  m=>m.version=2,m=>m.source='composed',m=>m.donor='other',m=>m.axisOrder='xyz',m=>m.byteOrder='big',
  m=>m.intensity.scale=2,m=>m.intensity.window.width=0,m=>m.coverage.missingChunk='acquired',
  m=>m.levels[0].dimensions[0]=10000,m=>m.levels[0].decodedBytes=1,
  m=>m.levels[0].labelVoxelToStage[3]+=.01,m=>m.levels[0].voxelToStage[0]*=2,
  m=>m.levels[0].chunks.labels.dimensions[0]++,m=>m.levels[0].chunks.labels.url='../other.bin',
  m=>m.labels[0].value=2,m=>m.labels[0].assetId='NLMCT:VHF:liver',
  m=>m.labels[0].geometrySha256='f'.repeat(64),m=>m.labels[0].provenance.source='composed',
  m=>m.region.initialVoxel[0]=-1,m=>m.attribution='',
]){
 const manifest=clone();mutate(manifest);assert.throws(()=>parseManifest(manifest));refused++;
}
for(const mutate of [
 m=>{m.levels[0].voxelToStage[3]+=.01;m.levels[0].labelVoxelToStage[3]+=.01;},
 m=>m.levels[0].voxelToSourcePhysical[3]+=1,
 m=>m.labels[0].bounds[0][0]+=.001,
 m=>m.inputs.ct.sha256='f'.repeat(64),
]){
 const manifest=clone();mutate(manifest);parseManifest(manifest);assert.throws(()=>bindAtlas(manifest,atlas));refused++;
}
const asset=async url=>{
 const path=new URL(url).pathname;
 if(path==='/atlases/nlm-vhf-ct.json')return readFile(resolve(root,'public'+path));
 return readFile(resolve(directory,path.split('/').pop()));
};
const fetcher=async url=>new Response(await asset(url));
const url='http://localhost/volumes/nlm-abdomen/manifest.json';
const loader=new VolumeLoader();
const volume=await loader.load(url,fetcher);
assert.deepEqual(volume.dimensions,[171,171,104]);assert.equal(volume.intensity.length,3041064);
await assert.rejects(()=>loader.load(url,async u=>u.endsWith('.bin')?new Response('missing',{status:404}):fetcher(u)),/missing asset/);
await assert.rejects(()=>loader.load(url,async u=>u.endsWith('.bin')?new Response(new Uint8Array(1)):fetcher(u)),/integrity failure/);
await assert.rejects(()=>loader.load(url,async u=>{
 const bytes=await asset(u);if(u.endsWith('.bin'))bytes[0]^=1;return new Response(bytes);
}),/integrity failure/);
await assert.rejects(()=>loader.load(url,async u=>u.includes('/atlases/')?new Response('{}'):fetcher(u)),/source atlas changed/);
// A server ignoring AbortSignal must still never deliver a cancelled or superseded volume.
let release;
const gate=new Promise(r=>release=r);
const stale=loader.load(url,async u=>{await gate;return fetcher(u);});
loader.cancel();release();await assert.rejects(()=>stale,/abort/i);
let releaseSecond;
const secondGate=new Promise(r=>releaseSecond=r);
const superseded=loader.load(url,async u=>{await secondGate;return fetcher(u);});
const caught=assert.rejects(()=>superseded,/abort/i);
const current=loader.load(url,fetcher);releaseSecond();await caught;await current;
console.log(`PASS: real package loading, ${refused} metadata/grid/identity corruptions, missing/truncated/tampered chunks, stale atlas, cancellation and superseded requests`);
