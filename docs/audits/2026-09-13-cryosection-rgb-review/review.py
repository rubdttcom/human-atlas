import json, hashlib, subprocess
from pathlib import Path
import h5py
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw

ROOT=Path('<repository root>')
OUT=Path('/tmp/cryo-audit-ivJcL2')
report=json.loads((ROOT/'generated/cryosection-alignment-check.json').read_text())
transform=json.loads((ROOT/'transforms/nlm-cryosection-to-vhf.json').read_text())
inventory=json.loads((ROOT/'generated/cryosection-inventory.json').read_text())
hashes={r['file']:r['sha256'] for r in inventory['files']}
rs={r['k']:r for r in report['slices']}
ts={r['k']:r for r in transform['per_slice']}
colors={}; names={}
for line in (ROOT/'data/raw/denver/extracted/Original Segmentation Labelmaps-mat_tif/VHF_Full_label_ColorTable.ctbl').read_text().splitlines():
    if line.startswith('#') or not line.strip(): continue
    p=line.split(); names[int(p[0])]=p[1];colors[int(p[0])]=list(map(int,p[2:5]))
ks=[7,500,1207,1210,1550,1893,1896,2259,2285,2295,2315,2500,3000,3532]
def ncc(a,b):
    a=a.astype(float)-a.mean();b=b.astype(float)-b.mean()
    return float(np.sum(a*b)/np.sqrt(np.sum(a*a)*np.sum(b*b)))
def boundary(labels):
    return (labels!=0)&((labels!=ndimage.maximum_filter(labels,3))|(labels!=ndimage.minimum_filter(labels,3)))
def rgbgray(a): return a@np.array([.299,.587,.114])
results=[]; panels=[]
with h5py.File(ROOT/'data/raw/denver/extracted/Original Segmentation Labelmaps-mat_tif/VHF_Full.mat') as h:
    scans=h['segmentation_data/scan_data'];labs=h['segmentation_data/label_data']
    for k in ks:
        tr=ts[k];row=rs[k];f=OUT/row['nlm_best'];raw=f.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==hashes[f.name]
        rgb=np.frombuffer(subprocess.check_output(['gzip','-dc',str(f)]),np.uint8).reshape(3,1216,2048).transpose(1,2,0)
        j,i=np.mgrid[0:434,0:666]; th=np.deg2rad(tr['theta_deg']);s=tr['s']
        c=s*(-np.cos(th)*i-np.sin(th)*j)+tr['tc'];r=s*(-np.sin(th)*i+np.cos(th)*j)+tr['tr']
        assert c.min()>=0 and r.min()>=0 and c.max()<=2047 and r.max()<=1215
        aligned=np.stack([ndimage.map_coordinates(rgb[...,ch].astype(float),[r,c],order=1) for ch in range(3)],axis=2)
        den=scans[k];label=labs[k];assert hashlib.sha256(den.tobytes()).hexdigest()==row['denver_sha256']
        gray=rgbgray(aligned);luma=rgbgray(rgb)
        shifted=ndimage.map_coordinates(luma,[r,c+6],order=1,mode='nearest')
        # Photometric fit only; geometry remains exactly the delivered transform.
        A=np.c_[aligned.reshape(-1,3),np.ones(434*666)]
        y=den.ravel(); train=(i.ravel()%2==0)&(j.ravel()%2==0)&(y>0)
        coef=np.linalg.lstsq(A[train],y[train],rcond=None)[0]
        test=(~train)&(y>0);pred=(A@coef).reshape(434,666)
        err=np.abs(pred-den)
        overlay=np.clip(aligned,0,255).astype(np.uint8);b=boundary(label)
        for lid in np.unique(label):
            if lid:overlay[b&(label==lid)]=colors[int(lid)]
        anatomy=[]
        for lid in np.unique(label):
            if not lid or 'Bone' not in names[int(lid)]:continue
            rr,cc=np.where(label==lid)
            anatomy.append({'label':names[int(lid)],'pixels':len(rr),'centroid_col':round(float(cc.mean()),1),'centroid_row':round(float(rr.mean()),1)})
        rec={'k':k,'photo':f.name,'identity_status':tr.get('identity_status'),'frame_margin':row['frame_choice']['margin'],
             'ncc':ncc(gray,den),'mirror_ncc':ncc(gray[:,::-1],den),'shift_6_rgb_px_ncc':ncc(shifted,den),
             'neighbor_ncc':{str(q):ncc(gray,scans[q]) for q in [k-1,k+1] if 0<=q<3533 and scans[q].max()>0},
             'photometric_holdout_mae':float(err.ravel()[test].mean()),'photometric_holdout_p95':float(np.quantile(err.ravel()[test],.95)),
             'bones':anatomy,'labels':{names[int(x)]:int((label==x).sum()) for x in np.unique(label) if x}}
        results.append(rec)
        tiles=[Image.fromarray(np.uint8(np.clip(aligned,0,255))),Image.fromarray(den).convert('RGB'),Image.fromarray(overlay),Image.fromarray(np.uint8(np.clip(err*8,0,255))).convert('RGB')]
        panel=Image.new('RGB',(1332,928),'#202020');d=ImageDraw.Draw(panel)
        for idx,(tile,title) in enumerate(zip(tiles,['RGB on Denver grid','Denver original grayscale','Denver ORIGINAL label boundaries','abs(gray-fit RGB - Denver) x8'])):
            x=(idx%2)*666;y0=30+(idx//2)*454;panel.paste(tile,(x,y0));d.text((x+5,y0-16),title,fill='white')
        d.text((8,4),f'k={k} {f.name} identity={tr.get("identity_status")} NCC={rec["ncc"]:.4f}',fill='yellow')
        path=OUT/f'panel-{k:04}.png';panel.save(path);panels.append(path)
        print(k,f.name,'ncc',round(rec['ncc'],4),'mirror',round(rec['mirror_ncc'],4),'shift',round(rec['shift_6_rgb_px_ncc'],4),flush=True)
    # blank reference bands and valid photos are different masks of availability
    blanks=[k for k in [0,6,1208,1209,1894,1895,2260,2284] if scans[k].max()==0]
    print('Checked Denver blank slices',blanks,flush=True)
for off in range(0,len(panels),4):
    sheet=Image.new('RGB',(1332,928),'white')
    for q,path in enumerate(panels[off:off+4]):sheet.paste(Image.open(path).resize((666,464)),((q%2)*666,(q//2)*464))
    sheet.save(OUT/f'sheet-{off//4}.jpg')
(OUT/'review-results.json').write_text(json.dumps({'revision':'02d3f59 geometry, working transform identity states','samples':results,'denver_blank_checks':blanks},indent=2))
