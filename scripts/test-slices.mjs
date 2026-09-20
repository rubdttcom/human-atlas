// Independent asymmetric phantom: analytical affine and scalar field, no production inverse in oracle.
import assert from 'node:assert/strict';
import {transform,inverseAffine,orthogonalPlane,obliquePlane,pixelPoint,projectPoint,translatePlane,directionLabel,dot} from '../app/slices/coordinates.ts';
import {sampleVoxel,sampleStage,windowValue} from '../app/slices/sampler.ts';
const near = (a,b,t=1e-4) => assert.ok(Math.abs(a-b)<=t,`${a} != ${b} within ${t}`);
const vector = (a,b,t=1e-4) => a.forEach((v,i)=>near(v,b[i],t));
// CT-like left/posterior/inferior columns, anisotropy, nonzero crop, rotation about stage y.
const angle=.31,c=Math.cos(angle),s=Math.sin(angle),crop=[11,17,23],spacing=[.002,.003,.004];
const raw = ([x,y,z]) => [c*x-s*y,z,-s*x-c*y];
const origin=[.13,.8,-.04];
const oracle = p => raw(p.map((v,i)=>(v+crop[i])*spacing[i])).map((v,i)=>v+origin[i]);
const zero=oracle([0,0,0]);
const axes=[[1,0,0],[0,1,0],[0,0,1]].map(p=>oracle(p).map((v,i)=>v-zero[i]));
const affine=[...Array.from({length:3},(_,r)=>[axes[0][r],axes[1][r],axes[2][r],zero[r]]).flat(),0,0,0,1];
const inverse=inverseAffine(affine),d=[9,7,5],n=d.reduce((a,b)=>a*b);
const volume={dimensions:d,voxelToStage:affine,stageToVoxel:inverse,intensity:new Float32Array(n),labels:new Uint8Array(n),support:new Uint8Array(n).fill(1)};
const index=(x,y,z)=>x+d[0]*(y+d[1]*z);
const field=([x,y,z])=>-1000+13*x+29*y+71*z;
for(let z=0;z<d[2];z++)for(let y=0;y<d[1];y++)for(let x=0;x<d[0];x++){
  volume.intensity[index(x,y,z)]=field([x,y,z]); volume.labels[index(x,y,z)]=x<3?1:x>5?2:0;
  const p=[x,y,z]; vector(transform(affine,p),oracle(p),1e-12); vector(transform(inverse,oracle(p)),p);
  const sample=sampleStage(volume,oracle(p)); assert.equal(sample.state,'acquired'); near(sample.hu,field(p),1e-3);
  assert.equal(sample.label,volume.labels[index(x,y,z)]);
}
for(let i=0;i<200;i++){
  const p=[(i*.137)%8,(i*.193)%6,(i*.071)%4];
  near(sampleStage(volume,oracle(p)).hu,field(p),1e-3);
}
const center=oracle([4,3,2]);
for(const view of ['axial','coronal','sagittal']){
  const plane=orthogonalPlane(affine,center,view);
  near(dot(plane.right,plane.up),0,1e-12); near(dot(plane.normal,plane.normal),1,1e-12);
  vector(pixelPoint(plane,50,40,101,81,.0002),center,1e-12);
  vector(projectPoint(plane,pixelPoint(plane,62,31,101,81,.0002)),[.0024,.0018,0],1e-12);
  const p=transform(inverse,pixelPoint(plane,51,40,101,81,.0002));
  assert.ok(p[view==='sagittal'?1:0] > (view==='sagittal'?3:4));
  const upper=transform(inverse,pixelPoint(plane,50,39,101,81,.0002));
  assert.ok(upper[view==='axial'?1:2]<(view==='axial'?3:2));
}
const axial=orthogonalPlane(affine,center,'axial');
for (const key of ['origin','right','up','normal']) vector(obliquePlane(axial,0,0)[key],axial[key],1e-12);
for(const angles of [[23,-47],[-90,90],[180,30]]){
  const p=obliquePlane(axial,...angles); vector(p.origin,center,1e-12); near(dot(p.right,p.up),0,1e-12);
  vector(projectPoint(p,translatePlane(p,.017).origin),[0,0,.017],1e-12);
  // Independent geometric oracle: rotate using explicit 3x3 Rodrigues matrices.
  const rotate=(v,a,deg)=>{
    const q=deg*Math.PI/180,C=Math.cos(q),S=Math.sin(q),[x,y,z]=a,T=1-C;
    const rows=[[C+x*x*T,x*y*T-z*S,x*z*T+y*S],[y*x*T+z*S,C+y*y*T,y*z*T-x*S],[z*x*T-y*S,z*y*T+x*S,C+z*z*T]];
    return rows.map(row=>row.reduce((acc,coefficient,i)=>acc+coefficient*v[i],0));
  };
  vector(p.right,rotate(rotate(axial.right,axial.right,angles[0]),axial.up,angles[1]),1e-12);
  for(let y=0;y<5;y++)for(let x=0;x<5;x++){
    const physical=pixelPoint(p,x,y,5,5,.0002);
    // Undo the independently specified rotation, translation, crop and anisotropy.
    const [X,Z,Y]=physical.map((v,i)=>v-origin[i]);
    const point=[(c*X-s*Y)/spacing[0]-crop[0],(-s*X-c*Y)/spacing[1]-crop[1],Z/spacing[2]-crop[2]];
    near(sampleStage(volume,physical).hu,field(point),1e-3);
  }
}
assert.equal(directionLabel([1,0,0]),'L'); assert.equal(directionLabel([0,-1,0]),'I'); assert.equal(directionLabel([1,0,1]),'LA');
// A left/right mirror must fail against the frozen field, rather than pass a self-consistent round trip.
assert.throws(()=>near(sampleVoxel(volume,[7,2,2]).hu,field([1,2,2]),1e-3));
const hole=index(4,3,2);volume.support[hole]=0;
assert.equal(sampleVoxel(volume,[3.5,3,2]).state,'outside-coverage');
assert.equal(sampleVoxel(volume,[3,3,2]).state,'acquired');
assert.equal(sampleStage(volume,oracle([3,3,2])).state,'acquired');
assert.equal(sampleVoxel(volume,[3+1e-8,3,2]).state,'outside-coverage');
assert.equal(sampleVoxel(volume,[-1,0,0]).state,'outside-coverage');
assert.equal(sampleVoxel(volume,[NaN,0,0]).state,'unavailable');
assert.equal(sampleVoxel({...volume,intensity:new Float32Array(0)},[0,0,0]).state,'unavailable');
assert.equal(sampleVoxel({...volume,labels:new Uint8Array(0)},[0,0,0]).state,'unavailable');
assert.equal(windowValue(50,400,50),.5);assert.equal(windowValue(-150,400,50),0);
assert.throws(()=>windowValue(0,0,50));assert.throws(()=>inverseAffine(new Array(16).fill(0)));
console.log('PASS: asymmetric/cropped affine, orthogonal and oblique sampling, mirror control, pixel synchronization, support, labels and window');
