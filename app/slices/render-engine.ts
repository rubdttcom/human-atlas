import * as T from 'three';
import type {Plane, Vec3, VolumeGrid} from './types.ts';
import {add,scale,transform} from './coordinates.ts';

export interface ImageSettings {width: number; level: number; selected: number; opacity: number; fill: boolean; color: string}
const vertex = `in vec3 position; void main(){gl_Position=vec4(position.xy,0.,1.);}`;
const fragment = `precision highp float;
precision highp sampler3D;
uniform sampler3D ct, labels, support;
uniform vec3 dims, origin, rightStep, upStep;
uniform vec2 size;
uniform float ww, wl, selected, opacity;
uniform bool fillMask, rawOutput;
uniform vec3 color;
out vec4 outputColor;
vec3 sampleAt(vec3 p){
 if(any(lessThan(p,vec3(-0.00001))) || any(greaterThan(p,dims-1.+0.00001)))return vec3(0.);
 p=clamp(p,vec3(0.),dims-1.);
 ivec3 low=ivec3(floor(p)), high=min(low+1,ivec3(dims)-1);
 vec3 f=p-vec3(low);float hu=0.;
 for(int z=0;z<2;z++)for(int y=0;y<2;y++)for(int x=0;x<2;x++){
   vec3 b=vec3(x,y,z);vec3 w=mix(1.-f,f,b);float weight=w.x*w.y*w.z;
   if(weight==0.)continue;
   ivec3 at=ivec3(x==0?low.x:high.x,y==0?low.y:high.y,z==0?low.z:high.z);
   if(texelFetch(support,at,0).r<.5/255.)return vec3(0.);
   hu+=texelFetch(ct,at,0).r*weight;
 }
 float label=floor(texelFetch(labels,ivec3(floor(p+.5)),0).r*255.+.5);
 return vec3(hu,label,1.);
}
void main(){
 vec2 offset=gl_FragCoord.xy-size*.5;
 vec3 p=origin+offset.x*rightStep+offset.y*upStep;
 vec3 a=sampleAt(p);
 if(rawOutput){outputColor=vec4(a,1.);return;}
 if(a.z<.5){float check=mod(floor(gl_FragCoord.x/8.)+floor(gl_FragCoord.y/8.),2.);outputColor=vec4(vec3(.07+.035*check),1.);return;}
 float grey=clamp((a.x-wl)/ww+.5,0.,1.);vec3 rgb=vec3(grey);
 if(selected>0. && a.y==selected){
   bool boundary=false;
   for(int i=0;i<4;i++){
     vec3 stepDir=i==0?rightStep:i==1?-rightStep:i==2?upStep:-upStep;
     vec3 neighbour=sampleAt(p+stepDir);
     if(neighbour.z<.5 || neighbour.y!=selected)boundary=true;
   }
   if(boundary || fillMask)rgb=mix(rgb,color,opacity);
 }
 outputColor=vec4(rgb,1.);
}`;

/** One GPU volume set per workspace; caller owns copied 2D canvases, not these textures. */
export class SliceRenderEngine {
  readonly renderer: T.WebGLRenderer;
  readonly memoryBytes: number;
  private scene = new T.Scene();
  private camera = new T.Camera();
  private geometry = new T.PlaneGeometry(2,2);
  private material: T.RawShaderMaterial;
  private textures: T.Data3DTexture[] = [];
  private volume: VolumeGrid;
  private lost = false;
  private onLost: (event: Event) => void;
  constructor(volume: VolumeGrid, onError: (message: string) => void) {
    this.volume = volume;
    const canvas=document.createElement('canvas');
    const context=canvas.getContext('webgl2',{antialias:false,alpha:false});
    if(!context)throw new Error('WebGL 2 is unavailable for slices. Enable WebGL and retry.');
    this.renderer=new T.WebGLRenderer({canvas,context,antialias:false,alpha:false});
    if(Math.max(...volume.dimensions)>context.getParameter(context.MAX_3D_TEXTURE_SIZE)){
      this.renderer.dispose();throw new Error('Preview exceeds this device’s 3D texture limit.');
    }
    this.renderer.setPixelRatio(1);
    this.onLost=e=>{e.preventDefault();this.lost=true;onError('Slice graphics context lost. Retry to reload the preview.');};
    canvas.addEventListener('webglcontextlost',this.onLost);
    const texture=(data:Float32Array|Uint8Array,type:T.TextureDataType)=>{
      if(!(data.buffer instanceof ArrayBuffer))throw new Error('Shared volume buffers are unsupported');
      const view=data instanceof Float32Array?new Float32Array(data.buffer,data.byteOffset,data.length):new Uint8Array(data.buffer,data.byteOffset,data.length);
      const t=new T.Data3DTexture(view,...volume.dimensions);t.format=T.RedFormat;t.type=type;
      t.minFilter=t.magFilter=T.NearestFilter;t.unpackAlignment=1;t.generateMipmaps=false;t.needsUpdate=true;
      this.textures.push(t);return t;
    };
    this.material=new T.RawShaderMaterial({glslVersion:T.GLSL3,vertexShader:vertex,fragmentShader:fragment,
      uniforms:{ct:{value:texture(volume.intensity,T.FloatType)},labels:{value:texture(volume.labels,T.UnsignedByteType)},support:{value:texture(volume.support,T.UnsignedByteType)},
        dims:{value:new T.Vector3(...volume.dimensions)},origin:{value:new T.Vector3()},rightStep:{value:new T.Vector3()},upStep:{value:new T.Vector3()},size:{value:new T.Vector2()},
        ww:{value:400},wl:{value:50},selected:{value:0},opacity:{value:.75},fillMask:{value:false},color:{value:new T.Vector3(1,0,0)},rawOutput:{value:false}}});
    this.scene.add(new T.Mesh(this.geometry,this.material));
    this.memoryBytes=volume.intensity.byteLength+volume.labels.byteLength+volume.support.byteLength;
  }
  private configure(plane:Plane,width:number,height:number,metresPerPixel:number,settings:ImageSettings) {
    if(this.lost)throw new Error('Slice graphics context lost; retry required');
    const origin=transform(this.volume.stageToVoxel,plane.origin);
    const delta=(v:Vec3)=>add(transform(this.volume.stageToVoxel,add(plane.origin,scale(v,metresPerPixel))),scale(origin,-1));
    const u=this.material.uniforms;
    u.origin.value.set(...origin);u.rightStep.value.set(...delta(plane.right));u.upStep.value.set(...delta(plane.up));u.size.value.set(width,height);
    u.ww.value=settings.width;u.wl.value=settings.level;u.selected.value=settings.selected;u.opacity.value=settings.opacity;u.fillMask.value=settings.fill;
    // Input is an sRGB UI color, output is display RGB without lighting/tone mapping.
    const rgb=settings.color.match(/[a-f0-9]{2}/gi)?.map(v=>parseInt(v,16)/255)??[1,0,0];u.color.value.set(...rgb);
  }
  render(target:HTMLCanvasElement,plane:Plane,width:number,height:number,metresPerPixel:number,settings:ImageSettings) {
    this.configure(plane,width,height,metresPerPixel,settings);
    this.material.uniforms.rawOutput.value=false;this.renderer.setRenderTarget(null);this.renderer.setSize(width,height,false);
    this.renderer.render(this.scene,this.camera);
    if(target.width!==width)target.width=width;if(target.height!==height)target.height=height;
    target.getContext('2d')!.drawImage(this.renderer.domElement,0,0);
  }
  /** Float readback for acceptance tests only; bottom row first as in WebGL. */
  readSamples(plane:Plane,width:number,height:number,metresPerPixel:number):Float32Array {
    if(!this.renderer.extensions.has('EXT_color_buffer_float'))throw new Error('Float diagnostic target unsupported');
    this.configure(plane,width,height,metresPerPixel,{width:400,level:50,selected:0,opacity:0,fill:false,color:'#ffffff'});
    const target=new T.WebGLRenderTarget(width,height,{type:T.FloatType,format:T.RGBAFormat,depthBuffer:false});
    try{this.material.uniforms.rawOutput.value=true;this.renderer.setRenderTarget(target);this.renderer.render(this.scene,this.camera);
      const result=new Float32Array(width*height*4);this.renderer.readRenderTargetPixels(target,0,0,width,height,result);return result;
    }finally{this.renderer.setRenderTarget(null);this.material.uniforms.rawOutput.value=false;target.dispose();}
  }
  dispose(){this.renderer.domElement.removeEventListener('webglcontextlost',this.onLost);this.textures.forEach(t=>t.dispose());this.geometry.dispose();this.material.dispose();this.renderer.dispose();this.renderer.forceContextLoss();}
}
