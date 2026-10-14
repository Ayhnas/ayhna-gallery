"""Browser setup and administration. Passwords and sessions are hashed in SQLite."""
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

def install_admin(app,db):
    with db() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS admin_sessions(token TEXT PRIMARY KEY,expires REAL);''')
    def get_setting(key):
        with db() as con:row=con.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row['value']) if row else None
    def password_record(password):
        salt=secrets.token_hex(24)
        return {'salt':salt,'digest':hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()}
    def matches(password):
        record=get_setting('password')
        if not record:return False
        digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(record['salt']),600000).hex()
        return secrets.compare_digest(digest,record['digest'])
    legacy=os.environ.get('GALLERY_PAIR_SECRET','')
    if legacy and not get_setting('password'):
        with db() as con:
            con.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('password',json.dumps(password_record(legacy))))
            con.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('name',json.dumps('AyhnaGallery NAS')))
    def ui_request(request:Request):
        origin=request.headers.get('origin')
        if request.headers.get('x-gallery-ui')!='1' or (origin and urlsplit(origin).netloc!=request.headers.get('host')):
            raise HTTPException(403,'설정 화면에서 요청하세요.')
    def admin(request:Request):
        raw=request.cookies.get('gallery_admin','')
        token=hashlib.sha256(raw.encode()).hexdigest()
        with db() as con:
            row=con.execute('SELECT expires FROM admin_sessions WHERE token=?',(token,)).fetchone()
        if not raw or not row or row['expires']<time.time():raise HTTPException(401,'관리자 로그인이 필요합니다.')
        return token
    def new_session(request,response):
        token=secrets.token_urlsafe(32)
        with db() as con:
            con.execute('DELETE FROM admin_sessions WHERE expires<?',(time.time(),))
            con.execute('INSERT INTO admin_sessions VALUES(?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time()+43200))
        response.set_cookie('gallery_admin',token,max_age=43200,httponly=True,samesite='strict',secure=request.url.scheme=='https')
    failures={}
    class Setup(BaseModel):
        name:str=Field(default='AyhnaGallery NAS',min_length=1,max_length=100)
        password:str=Field(min_length=8,max_length=256)
    class Login(BaseModel):
        password:str=Field(min_length=1,max_length=256)
    class Name(BaseModel):
        name:str=Field(min_length=1,max_length=100)
    @app.get('/',response_class=HTMLResponse)
    def home():
        return HTMLResponse(Path(__file__).with_name('admin.html').read_text(encoding='utf-8'),headers={
            'Cache-Control':'no-store','X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"})
    @app.get('/admin/state')
    def state():return {'configured':bool(get_setting('password'))}
    @app.post('/admin/setup',dependencies=[Depends(ui_request)])
    def setup(body:Setup,request:Request,response:Response):
        record=password_record(body.password)
        with db() as con:
            cursor=con.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('password',json.dumps(record)))
            if not cursor.rowcount:raise HTTPException(409,'이미 설정된 서버입니다. 로그인하세요.')
            con.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('name',json.dumps(body.name,ensure_ascii=False)))
        new_session(request,response);return {'ok':True}
    @app.post('/admin/login',dependencies=[Depends(ui_request)])
    def login(body:Login,request:Request,response:Response):
        peer=request.client.host if request.client else 'unknown';now=time.time()
        recent=[t for t in failures.get(peer,[]) if t>now-60]
        if len(recent)>=10:raise HTTPException(429,'잠시 후 다시 로그인하세요.')
        if not matches(body.password):
            if len(failures)>2048:failures.clear()
            failures[peer]=recent+[now];raise HTTPException(403,'비밀번호가 올바르지 않습니다.')
        failures.pop(peer,None);new_session(request,response);return {'ok':True}
    @app.post('/admin/logout',dependencies=[Depends(ui_request)])
    def logout(response:Response,token=Depends(admin)):
        with db() as con:con.execute('DELETE FROM admin_sessions WHERE token=?',(token,))
        response.delete_cookie('gallery_admin');return {'ok':True}
    @app.get('/admin/overview')
    def overview(token=Depends(admin)):
        with db() as con:
            rows=con.execute('''SELECT d.id,d.name,d.last_seen,(d.token!='') AS registered,
            COUNT(m.id) AS photos FROM devices d LEFT JOIN media m ON m.device=d.id
            GROUP BY d.id ORDER BY d.name''').fetchall()
            total=con.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(thumb)),0) FROM media').fetchone()
        return {'name':get_setting('name') or 'AyhnaGallery NAS','devices':[dict(r,online=bool(r['registered']) and time.time()-r['last_seen']<60) for r in rows],
                'photos':total[0],'thumbnail_bytes':total[1],'version':app.version}
    @app.post('/admin/settings',dependencies=[Depends(ui_request)])
    def settings(body:Name,token=Depends(admin)):
        with db() as con:con.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('name',json.dumps(body.name,ensure_ascii=False)))
        return {'ok':True}
    @app.post('/admin/password',dependencies=[Depends(ui_request)])
    def password(body:Setup,token=Depends(admin)):
        with db() as con:
            con.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('password',json.dumps(password_record(body.password))))
            con.execute('DELETE FROM admin_sessions')
        return {'ok':True}
    @app.post('/admin/devices/{ident}/rename',dependencies=[Depends(ui_request)])
    def rename(ident:str,body:Name,token=Depends(admin)):
        with db() as con:con.execute('UPDATE devices SET name=? WHERE id=?',(body.name,ident))
        return {'ok':True}
    @app.post('/admin/devices/{ident}/disconnect',dependencies=[Depends(ui_request)])
    def disconnect(ident:str,token=Depends(admin)):
        with db() as con:
            con.execute("UPDATE devices SET token='',last_seen=0 WHERE id=?",(ident,))
            con.execute('UPDATE media SET available=0 WHERE device=?',(ident,))
            con.execute("UPDATE requests SET status='failed',error='기기 등록 해제' WHERE status IN ('queued','waiting') AND (receiver=? OR media IN (SELECT id FROM media WHERE device=?))",(ident,ident))
        return {'ok':True}
    return matches
