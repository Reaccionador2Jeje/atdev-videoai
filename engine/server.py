#!/usr/bin/env python3
import json, os, re, shutil, subprocess, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'renders'
OUT.mkdir(exist_ok=True)
PORT=int(os.environ.get('ATDEV_PORT','8765'))
FORMATS={'16:9':(1280,720),'9:16':(720,1280),'1:1':(720,720)}
HEX=re.compile(r'^#[0-9a-fA-F]{6}$')

def esc(value):
    return str(value or '').replace('\\','\\\\').replace(':','\\:').replace("'","\\'").replace('%','\\%').replace(',','\\,')[:160]

def render(data):
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFmpeg is not installed or not on PATH.')
    scenes=data.get('scenes')
    if not isinstance(scenes,list) or not scenes or len(scenes)>30:
        raise ValueError('Add between 1 and 30 scenes.')
    fmt=data.get('format','16:9')
    if fmt not in FORMATS: raise ValueError('Invalid video format.')
    w,h=FORMATS[fmt]
    with tempfile.TemporaryDirectory() as tmp:
        parts=[]
        for i,s in enumerate(scenes):
            dur=max(1,min(30,int(s.get('duration',5))))
            bg=s.get('background','#18221d')
            if not isinstance(bg,str) or not HEX.match(bg): bg='#18221d'
            filters=[]
            title=esc(s.get('title'))
            sub=esc(s.get('subtitle'))
            if title: filters.append("drawtext=text='"+title+"':fontcolor=white:fontsize="+str(max(26,w//22))+":x=(w-text_w)/2:y=h*0.39")
            if sub: filters.append("drawtext=text='"+sub+"':fontcolor=0xD5DEC9:fontsize="+str(max(16,w//42))+":x=(w-text_w)/2:y=h*0.56")
            dest=Path(tmp)/('scene-%03d.mp4'%i)
            cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i',f'color=c={bg}:s={w}x{h}:r=30:d={dur}','-vf',','.join(filters) if filters else 'null','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-an',str(dest)]
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            if p.returncode: raise RuntimeError(p.stderr[-1000:])
            parts.append(dest)
        listing=Path(tmp)/'concat.txt'
        listing.write_text(''.join("file '"+str(p)+"'\n" for p in parts))
        name='video-'+os.urandom(6).hex()+'.mp4'
        dest=OUT/name
        p=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(dest)],capture_output=True,text=True,timeout=180)
        if p.returncode: raise RuntimeError(p.stderr[-1000:])
    return name

class API(BaseHTTPRequestHandler):
    def reply(self,status,obj):
        b=json.dumps(obj).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Content-Type'); self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self): self.reply(200,{'ok':True})
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/health': self.reply(200,{'ok':True,'ffmpeg':bool(shutil.which('ffmpeg'))}); return
        if path.startswith('/renders/'):
            name=Path(path).name
            if not re.fullmatch(r'video-[a-f0-9]+\.mp4',name): self.send_error(404); return
            f=OUT/name
            if not f.is_file(): self.send_error(404); return
            self.send_response(200); self.send_header('Content-Type','video/mp4'); self.send_header('Content-Length',str(f.stat().st_size)); self.end_headers()
            with f.open('rb') as stream: shutil.copyfileobj(stream,self.wfile)
            return
        self.reply(404,{'error':'Not found'})
    def do_POST(self):
        if urlparse(self.path).path!='/api/render': self.reply(404,{'error':'Not found'}); return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 1<=size<=2*1024*1024: raise ValueError('Invalid request size.')
            name=render(json.loads(self.rfile.read(size)))
            self.reply(200,{'ok':True,'filename':name,'url':f'http://127.0.0.1:{PORT}/renders/{name}'})
        except Exception as e: self.reply(400,{'error':str(e)})
    def log_message(self,*args): pass

if __name__=='__main__':
    print(f'AtDev VideoAI engine at http://127.0.0.1:{PORT}')
    ThreadingHTTPServer(('127.0.0.1',PORT),API).serve_forever()
