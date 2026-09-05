import fs from 'node:fs';
import assert from 'node:assert/strict';
const filename=process.argv[2]??'atlas.json';
const base=new URL('../public/models/',import.meta.url),atlas=JSON.parse(fs.readFileSync(new URL(filename,base)));
const EXPECTED={'atlas.json':[2234,3432],'atlas-female.json':[888,1073],'atlas-tcia-female.json':[36,36],'atlas-denver-female.json':[128,203],'atlas-nlm-vhf-ct.json':[114,148]};
const expected=EXPECTED[filename];if(!expected)throw new Error(`No expectation recorded for ${filename}`);
assert.equal(atlas.parts.length,expected[0]);assert.equal(atlas.concepts.length,expected[1]);
const ids=new Set(atlas.parts.map(p=>p.id));assert.equal(ids.size,expected[0]);
const files=atlas.chunks.map(c=>{const b=fs.readFileSync(new URL(c.url.split('/').pop(),base));assert.equal(b.length,c.bytes);return b;});
let tris=0;
for(const p of atlas.parts){assert.ok(p.name.trim()&&p.name!=='-'&&!p.name.includes('Bounds('));assert.ok(p.conceptId!=='-');assert.ok(p.system);const b=files[p.chunk];assert.ok(p.indices+p.indexCount*4<=b.length);const pos=new Float32Array(b.buffer,b.byteOffset+p.positions,p.vertexCount*3),indices=new Uint32Array(b.buffer,b.byteOffset+p.indices,p.indexCount);assert.ok(indices.length>=3);for(const i of indices)assert.ok(i<p.vertexCount,`${p.id}: invalid vertex`);for(const value of pos)assert.ok(Number.isFinite(value));tris+=p.indexCount/3;}
for(const c of atlas.concepts){assert.ok(c.elements.length);for(const id of c.elements)assert.ok(ids.has(id),`${c.id}: missing ${id}`);}
assert.equal(tris,atlas.triangles);
console.log(`Verified ${ids.size} individually indexed meshes, ${atlas.concepts.length} complete concept mappings, ${tris.toLocaleString()} triangles, and every binary buffer.`);
