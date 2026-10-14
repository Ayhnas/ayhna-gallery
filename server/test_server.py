"""Actual HTTP integration tests, including simultaneous upload/download streaming."""
import base64
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from PIL import Image

class ProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        with socket.socket() as s:
            s.bind(('127.0.0.1',0)); cls.port=s.getsockname()[1]
        cls.url=f'http://127.0.0.1:{cls.port}'
        env={**os.environ,'GALLERY_DATA':cls.temp.name,'GALLERY_PAIR_SECRET':'test-only-secret'}
        cls.log=open(Path(cls.temp.name)/'server.log','w')
        cls.proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(cls.port),'--no-access-log'],cwd=Path(__file__).parent,env=env,stdout=cls.log,stderr=cls.log)
        cls.client=httpx.Client(base_url=cls.url,timeout=35)
        for _ in range(100):
            try:
                if cls.client.get('/health').status_code==200:break
            except httpx.ConnectError:pass
            time.sleep(.1)
        else:raise RuntimeError('server startup failed')
        cls.a=cls.client.post('/pair',json={'secret':'test-only-secret','name':'폰'}).json()
        cls.b=cls.client.post('/pair',json={'secret':'test-only-secret','name':'PC'}).json()
        cls.ah={'Authorization':'Bearer '+cls.a['token']};cls.bh={'Authorization':'Bearer '+cls.b['token']}
        cls.raw=os.urandom(1500000)
        img=Image.new('RGB',(800,600),'navy');buf=io.BytesIO();img.save(buf,'JPEG')
        cls.payload={'local_id':'content://images/1','album':'카메라','filename':'one.jpg','mime':'image/jpeg','taken_ms':1234567890123,
            'sha256':hashlib.sha256(cls.raw).hexdigest(),'bytes':len(cls.raw),'metadata':{'apps':[{'name':'Discord','percent':93.5}]},'thumbnail':base64.b64encode(buf.getvalue()).decode()}
        cls.photo=cls.client.post('/media',json=cls.payload,headers=cls.ah).json()['id']
    @classmethod
    def tearDownClass(cls):
        cls.client.close();cls.proc.terminate();cls.proc.wait(timeout=10);cls.log.close();cls.temp.cleanup()
    def test_01_auth_pairing(self):
        self.assertEqual(self.client.get('/devices').status_code,401)
        self.assertEqual(self.client.post('/pair',json={'secret':'bad','name':'X'}).status_code,403)
        self.assertEqual(len(self.client.get('/devices',headers=self.bh).json()),2)
    def test_02_catalog_idempotent_and_thumbnail(self):
        self.assertEqual(self.client.post('/media',json=self.payload,headers=self.ah).json()['id'],self.photo)
        listing=self.client.get('/media',headers=self.bh).json()
        self.assertEqual(len(listing),1);self.assertEqual(listing[0]['metadata'],self.payload['metadata'])
        thumb=self.client.get(f'/media/{self.photo}/thumb',headers=self.bh)
        with Image.open(io.BytesIO(thumb.content)) as im:self.assertLessEqual(max(im.size),512)
        self.assertNotIn('thumb',listing[0])
    def test_03_relay_without_original_storage(self):
        req=self.client.post('/requests',headers=self.bh,json={'media_id':self.photo}).json()['id']
        self.assertEqual(self.client.get(f'/requests/{req}',headers=self.ah).status_code,404)
        with ThreadPoolExecutor(2) as pool:
            download=pool.submit(lambda:httpx.get(self.url+f'/requests/{req}/content',headers=self.bh,timeout=40))
            task=self.client.get('/tasks',headers=self.ah).json()[0]
            self.assertEqual(task['id'],req)
            self.assertEqual(task['local_id'],self.payload['local_id'])
            denied=self.client.put(f'/requests/{req}/content',headers=self.bh,content=self.raw)
            self.assertEqual(denied.status_code,409)
            uploaded=self.client.put(f'/requests/{req}/content',headers=self.ah,content=(self.raw[i:i+65536] for i in range(0,len(self.raw),65536)))
            self.assertEqual(uploaded.status_code,200,uploaded.text)
            response=download.result(timeout=40)
        self.assertEqual(response.content,self.raw)
        self.assertEqual(self.client.get(f'/requests/{req}',headers=self.bh).json()['status'],'complete')
        files=list(Path(self.temp.name).iterdir())
        self.assertTrue(all(p.name.startswith('catalog.sqlite3') or p.name=='server.log' for p in files))
    def test_04_missing_original_feedback(self):
        req=self.client.post('/requests',headers=self.bh,json={'media_id':self.photo}).json()['id']
        with ThreadPoolExecutor(1) as pool:
            download=pool.submit(lambda:httpx.get(self.url+f'/requests/{req}/content',headers=self.bh,timeout=40))
            self.client.get('/tasks',headers=self.ah)
            self.client.post(f'/requests/{req}/fail',headers=self.ah)
            result=download.result(timeout=40)
        self.assertEqual(result.status_code,409)
        self.assertIn('원본',result.json()['detail'])
    def test_05_owner_can_revoke(self):
        self.client.delete(f'/media/{self.photo}',headers=self.bh)
        self.assertEqual(self.client.get('/media',headers=self.ah).json()[0]['available'],1)
        self.client.delete(f'/media/{self.photo}',headers=self.ah)
        self.assertEqual(self.client.post('/requests',headers=self.bh,json={'media_id':self.photo}).status_code,404)
        self.client.post('/media',headers=self.ah,json=self.payload)
    def test_06_invalid_hash_rejected(self):
        bad={**self.payload,'sha256':'bad'}
        self.assertEqual(self.client.post('/media',json=bad,headers=self.ah).status_code,422)

if __name__=='__main__':unittest.main(verbosity=2)
