// Executed in the browser by browser-check-slices.py. Independent analytical phantom.
import {SliceRenderEngine} from '../app/slices/render-engine.ts';
import {inverseAffine,orthogonalPlane,obliquePlane,pixelPoint} from '../app/slices/coordinates.ts';

export function checkShaderPhantom(){
  const angle=.31,c=Math.cos(angle),s=Math.sin(angle),crop=[11,17,23],spacing=[.002,.003,.004],translation=[.13,.8,-.04];
  const physical=p=>{const [x,y,z]=p.map((v,i)=>(v+crop[i])*spacing[i]);return [c*x-s*y+translation[0],z+translation[1],-s*x-c*y+translation[2]];};
  const inverse=p=>{const x=p[0]-translation[0],z=p[1]-translation[1],y=p[2]-translation[2];return [(c*x-s*y)/spacing[0]-crop[0],(-s*x-c*y)/spacing[1]-crop[1],z/spacing[2]-crop[2]];};
  const origin=physical([0,0,0]),columns=[[1,0,0],[0,1,0],[0,0,1]].map(p=>physical(p).map((v,i)=>v-origin[i]));
  const affine=[...Array.from({length:3},(_,i)=>[columns[0][i],columns[1][i],columns[2][i],origin[i]]).flat(),0,0,0,1];
  const dimensions=[9,7,5],n=315,index=(x,y,z)=>x+9*(y+7*z),field=([x,y,z])=>-1000+13*x+29*y+71*z;
  const volume={dimensions,voxelToStage:affine,stageToVoxel:inverseAffine(affine),intensity:new Float32Array(n),labels:new Uint8Array(n),support:new Uint8Array(n).fill(1)};
  for(let z=0;z<5;z++)for(let y=0;y<7;y++)for(let x=0;x<9;x++){volume.intensity[index(x,y,z)]=field([x,y,z]);volume.labels[index(x,y,z)]=x<3?1:x>5?2:0;}
  let engine=new SliceRenderEngine(volume,message=>{throw Error(message)}),maximumError=0,nativeCentres=0,tiltedSamples=0;
  const assert=(condition,message)=>{if(!condition)throw Error(message);};
  const inspect=(plane,point)=>{
    const values=engine.readSamples({...plane,origin:physical(point)},1,1,.001);
    assert(values[2]===1,'Native centre lost support');
    maximumError=Math.max(maximumError,Math.abs(values[0]-field(point)));
    assert(values[1]===volume.labels[index(...point)],'Native label changed');nativeCentres++;
  };
  const axial=orthogonalPlane(affine,physical([4,3,2]),'axial');
  for(let z=0;z<5;z++)for(let y=0;y<7;y++)for(let x=0;x<9;x++)inspect(axial,[x,y,z]);
  for(const plane of [axial,orthogonalPlane(affine,axial.origin,'coronal'),orthogonalPlane(affine,axial.origin,'sagittal'),obliquePlane(axial,23,-47),obliquePlane(axial,-61,31)]){
    const values=engine.readSamples(plane,12,12,.0002);
    for(let y=0;y<12;y++)for(let x=0;x<12;x++){
      const point=inverse(pixelPoint(plane,x,y,12,12,.0002)),offset=((11-y)*12+x)*4;
      assert(values[offset+2]===1,'Interior phantom support disappeared');
      maximumError=Math.max(maximumError,Math.abs(values[offset]-field(point)));tiltedSamples++;
    }
  }
  assert(maximumError<=.1,'Shader exceeds frozen 0.1 HU tolerance');
  const mirror=engine.readSamples({...axial,origin:physical([7,3,2])},1,1,.001)[0];
  assert(Math.abs(mirror-field([1,3,2]))>.1,'Mirror negative control did not fail');
  assert(engine.renderer.info.memory.textures===3,'Unexpected retained diagnostic texture count');
  engine.dispose();
  assert(engine.renderer.info.memory.textures===0,'Volume textures retained after disposal');
  volume.support[index(4,3,2)]=0;
  engine=new SliceRenderEngine(volume,message=>{throw Error(message)});
  const validity=point=>engine.readSamples({...axial,origin:physical(point)},1,1,.001)[2];
  assert(validity([3,3,2])===1,'Adjacent integer centre incorrectly excluded');
  assert(validity([3.5,3,2])===0,'Interpolated across excluded voxel');
  assert(validity([-1,3,2])===0,'Outside volume acquired');
  assert(validity([4,3,2])===0,'Excluded voxel acquired');
  engine.dispose();
  assert(engine.renderer.info.memory.textures===0,'Second volume textures retained');
  return {nativeCentres,tiltedSamples,maximumError,mirrorControl:'failed as required',gapControls:'passed',retainedTexturesAfterDispose:0};
}
