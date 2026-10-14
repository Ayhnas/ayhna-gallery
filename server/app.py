"""Single-household catalogue. Originals are relayed in bounded RAM, never written to NAS."""
import asyncio
import base64
import hashlib
import io
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

DATA = Path(os.environ.get('GALLERY_DATA', './data'))
DATA.mkdir(parents=True, exist_ok=True)
MAX_ORIGINAL = 256 * 1024 * 1024

@contextmanager
def db():
    con = sqlite3.connect(DATA / 'catalog.sqlite3')
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    try:
        with con:
            yield con
    finally:
        con.close()

with db() as con:
    con.executescript('''
    CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,name TEXT,token TEXT,last_seen REAL);
    CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY,device TEXT,local_id TEXT,album TEXT,
        filename TEXT,mime TEXT,taken_ms INTEGER,sha256 TEXT,bytes INTEGER,metadata TEXT,thumb BLOB,
        available INTEGER DEFAULT 1,UNIQUE(device,local_id));
    CREATE INDEX IF NOT EXISTS media_device_date ON media(device,taken_ms);
    CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,receiver TEXT,media TEXT,
        status TEXT,created REAL,lease REAL DEFAULT 0,error TEXT DEFAULT '');
    ''')
    con.execute("UPDATE requests SET status='queued',lease=0 WHERE status IN ('waiting','sending')")

def one(sql, args=()):
    with db() as con:
        row = con.execute(sql, args).fetchone()
    return dict(row) if row else None

def execute(sql, args=()):
    with db() as con:
        con.execute(sql, args)

async def device(request: Request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(401, '기기 인증이 필요합니다.')
    token = hashlib.sha256(auth[7:].encode()).hexdigest()
    item = one('SELECT * FROM devices WHERE token=?', (token,))
    if not item:
        raise HTTPException(401, '기기 인증이 유효하지 않습니다.')
    execute('UPDATE devices SET last_seen=? WHERE id=?', (time.time(), item['id']))
    return item

class Relay:
    def __init__(self):
        self.queue = asyncio.Queue(maxsize=8)
        self.closed = asyncio.Event()
        self.uploading = False

relays: dict[str, Relay] = {}

@asynccontextmanager
async def lifespan(app):
    async def cleanup():
        while True:
            execute("UPDATE requests SET status='expired',error='요청 유효기간 만료' WHERE created<? AND status IN ('queued','waiting')", (time.time()-86400,))
            await asyncio.sleep(30)
    task = asyncio.create_task(cleanup())
    yield
    task.cancel()
    for relay in relays.values():
        relay.closed.set()

app = FastAPI(title='AyhnaGallery', version='0.2.0', lifespan=lifespan)
from admin import install_admin
password_matches = install_admin(app, db)

class Pair(BaseModel):
    secret: str
    name: str = Field(min_length=1, max_length=100)

@app.get('/health')
def health():
    return {'ok': True, 'protocol': 1}

@app.post('/pair')
def pair(body: Pair):
    if not password_matches(body.secret):
        raise HTTPException(403, '서버 연결 비밀번호가 올바르지 않습니다. NAS의 웹 설정을 확인하세요.')
    token, ident = secrets.token_urlsafe(32), str(uuid.uuid4())
    execute('INSERT INTO devices VALUES(?,?,?,?)', (ident, body.name, hashlib.sha256(token.encode()).hexdigest(), time.time()))
    return {'id': ident, 'token': token}

@app.get('/devices')
def devices(me=Depends(device)):
    with db() as con:
        rows = con.execute('SELECT id,name,last_seen FROM devices ORDER BY name').fetchall()
    return [dict(r, online=time.time()-r['last_seen']<60) for r in rows]

class Photo(BaseModel):
    local_id: str = Field(min_length=1, max_length=512)
    album: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=255)
    mime: str = Field(max_length=100)
    taken_ms: int
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    bytes: int = Field(gt=0, le=MAX_ORIGINAL)
    metadata: dict = Field(default_factory=dict)
    thumbnail: str = Field(max_length=400000)

@app.post('/media')
def upsert(body: Photo, me=Depends(device)):
    metadata = json.dumps(body.metadata, ensure_ascii=False)
    if len(metadata.encode()) > 65536:
        raise HTTPException(413, '메타데이터가 너무 큽니다.')
    try:
        raw = base64.b64decode(body.thumbnail, validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            if im.width*im.height > 4_000_000:
                raise ValueError('too large')
            im = ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((512,512))
            buf = io.BytesIO(); im.save(buf, 'JPEG', quality=65)
            thumb = buf.getvalue()
    except Exception:
        raise HTTPException(400, '썸네일 형식이 올바르지 않습니다.')
    ident = str(uuid.uuid5(uuid.NAMESPACE_URL, me['id']+'\n'+body.local_id))
    with db() as con:
        con.execute('''INSERT INTO media VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
        ON CONFLICT(device,local_id) DO UPDATE SET album=excluded.album,filename=excluded.filename,
        mime=excluded.mime,taken_ms=excluded.taken_ms,sha256=excluded.sha256,bytes=excluded.bytes,
        metadata=excluded.metadata,thumb=excluded.thumb,available=1''',
        (ident,me['id'],body.local_id,body.album,body.filename,body.mime,body.taken_ms,body.sha256,body.bytes,metadata,thumb))
    return {'id': ident}

@app.delete('/media/{ident}')
def remove(ident: str, me=Depends(device)):
    execute('UPDATE media SET available=0 WHERE id=? AND device=?', (ident,me['id']))
    return {'ok': True}

@app.get('/media')
def listing(device_id: str='', offset: int=0, limit: int=100, me=Depends(device)):
    with db() as con:
        rows = con.execute('''SELECT id,device,local_id,album,filename,mime,taken_ms,sha256,bytes,metadata,available
        FROM media WHERE (?='' OR device=?) ORDER BY taken_ms DESC,id LIMIT ? OFFSET ?''',
        (device_id,device_id,max(1,min(limit,200)),max(0,offset))).fetchall()
    return [dict(r, metadata=json.loads(r['metadata'])) for r in rows]

@app.get('/media/{ident}/thumb')
def thumbnail(ident: str, me=Depends(device)):
    row = one('SELECT thumb FROM media WHERE id=?', (ident,))
    if not row: raise HTTPException(404)
    return Response(row['thumb'], media_type='image/jpeg', headers={'Cache-Control':'private, max-age=86400'})

class Fetch(BaseModel):
    media_id: str

@app.post('/requests')
def create_request(body: Fetch, me=Depends(device)):
    photo = one('SELECT * FROM media WHERE id=?', (body.media_id,))
    if not photo or not photo['available']: raise HTTPException(404, '원본이 더 이상 제공되지 않습니다.')
    ident = str(uuid.uuid4())
    execute('INSERT INTO requests(id,receiver,media,status,created) VALUES(?,?,?,?,?)', (ident,me['id'],body.media_id,'queued',time.time()))
    return {'id': ident, 'status':'queued'}

@app.get('/requests/{ident}')
def status(ident: str, me=Depends(device)):
    item = one('SELECT id,status,error FROM requests WHERE id=? AND receiver=?', (ident,me['id']))
    if not item: raise HTTPException(404)
    return item

@app.get('/tasks')
async def tasks(me=Depends(device)):
    deadline = time.monotonic()+20
    while time.monotonic()<deadline:
        with db() as con:
            rows = con.execute('''SELECT r.id,m.local_id,m.sha256,m.bytes FROM requests r JOIN media m ON r.media=m.id
            WHERE m.device=? AND r.status='waiting' AND r.lease<? ORDER BY r.created LIMIT 4''', (me['id'],time.time())).fetchall()
            for row in rows:
                con.execute('UPDATE requests SET lease=? WHERE id=?', (time.time()+35,row['id']))
        if rows: return [dict(r) for r in rows]
        await asyncio.sleep(.2)
    return []

@app.get('/requests/{ident}/content')
async def content(ident: str, request: Request, me=Depends(device)):
    row = one('SELECT r.*,m.mime FROM requests r JOIN media m ON r.media=m.id WHERE r.id=? AND receiver=?', (ident,me['id']))
    if not row: raise HTTPException(404)
    if row['status'] not in ('queued','waiting'): raise HTTPException(409, row['error'] or row['status'])
    if ident in relays: raise HTTPException(409, '이미 불러오는 중입니다.')
    relay = Relay(); relays[ident] = relay
    execute("UPDATE requests SET status='waiting',lease=0 WHERE id=?", (ident,))
    async def first():
        while True:
            if await request.is_disconnected(): raise asyncio.CancelledError()
            try: return await asyncio.wait_for(relay.queue.get(), .5)
            except asyncio.TimeoutError: pass
    try:
        initial = await asyncio.wait_for(first(), 25)
        if isinstance(initial, Exception): raise HTTPException(409, str(initial))
    except BaseException as exc:
        relay.closed.set(); relays.pop(ident,None)
        execute("UPDATE requests SET status='queued',lease=0 WHERE id=? AND status IN ('waiting','sending')", (ident,))
        if isinstance(exc, asyncio.TimeoutError): raise HTTPException(409, '기기 응답 대기 — 원본 기기에서 앱을 열고 다시 시도하세요.')
        raise
    async def stream():
        try:
            if initial is not None: yield initial
            while True:
                item = await asyncio.wait_for(relay.queue.get(), 40)
                if item is None: break
                if isinstance(item, Exception): raise RuntimeError(str(item))
                yield item
        finally:
            relay.closed.set(); relays.pop(ident,None)
            execute("UPDATE requests SET status='queued',lease=0 WHERE id=? AND status IN ('waiting','sending')", (ident,))
    return StreamingResponse(stream(), media_type=row['mime'], headers={'Cache-Control':'no-store'})

@app.post('/requests/{ident}/fail')
def failed(ident: str, me=Depends(device)):
    row = one('SELECT r.id FROM requests r JOIN media m ON r.media=m.id WHERE r.id=? AND m.device=?', (ident,me['id']))
    if not row: raise HTTPException(404)
    execute("UPDATE requests SET status='failed',error='원본이 없거나 접근 권한이 없습니다.' WHERE id=?", (ident,))
    relay = relays.get(ident)
    if relay and not relay.queue.full(): relay.queue.put_nowait(ValueError('원본이 없거나 접근 권한이 없습니다.'))
    return {'ok': True}

@app.put('/requests/{ident}/content')
async def upload(ident: str, request: Request, me=Depends(device)):
    row = one('SELECT r.*,m.sha256,m.bytes FROM requests r JOIN media m ON r.media=m.id WHERE r.id=? AND m.device=?', (ident,me['id']))
    relay = relays.get(ident)
    if not row or not relay or relay.closed.is_set(): raise HTTPException(409, '수신 기기가 연결되어 있지 않습니다.')
    if relay.uploading: raise HTTPException(409, '전송 중입니다.')
    relay.uploading = True
    execute("UPDATE requests SET status='sending' WHERE id=?", (ident,))
    count = 0; digest = hashlib.sha256()
    async def put(chunk):
        if relay.closed.is_set(): raise ValueError('수신 기기 연결 종료')
        await asyncio.wait_for(relay.queue.put(chunk), 30)
        if relay.closed.is_set(): raise ValueError('수신 기기 연결 종료')
    try:
        async for data in request.stream():
            count += len(data); digest.update(data)
            if count > row['bytes'] or count > MAX_ORIGINAL: raise ValueError('원본 크기 불일치')
            for start in range(0,len(data),65536): await put(data[start:start+65536])
        if count != row['bytes'] or digest.hexdigest()!=row['sha256']: raise ValueError('원본 검증 실패 — 파일이 변경되었습니다.')
        execute("UPDATE requests SET status='complete',error='' WHERE id=?", (ident,))
        await put(None)
    except Exception as error:
        execute("UPDATE requests SET status='failed',error=? WHERE id=?", (str(error),ident))
        if not relay.closed.is_set():
            try: await asyncio.wait_for(relay.queue.put(error), 2)
            except asyncio.TimeoutError: pass
        raise HTTPException(409, str(error))
    return {'ok': True}
