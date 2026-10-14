import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
import httpx

class AdminTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.url=f'http://127.0.0.1:{port}'
        self.env={**os.environ,'GALLERY_DATA':self.temp.name};self.env.pop('GALLERY_PAIR_SECRET',None)
        self.log=open(Path(self.temp.name)/'server.log','w')
        self.start(port)
        self.client=httpx.Client(base_url=self.url,headers={'X-Gallery-UI':'1','Origin':self.url},timeout=10)
    def start(self,port):
        self.port=port
        self.process=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],cwd=Path(__file__).parent,env=self.env,stdout=self.log,stderr=self.log)
        for _ in range(100):
            try:
                if httpx.get(self.url+'/health',timeout=1).is_success:break
            except httpx.ConnectError:pass
            time.sleep(.05)
        else:raise RuntimeError('Server startup failed')
    def tearDown(self):
        self.client.close();self.process.terminate();self.process.wait(timeout=10);self.log.close();self.temp.cleanup()
    def test_gui_setup_auth_management_password_and_persistence(self):
        c=self.client
        self.assertIn('NAS 서버를 시작',c.get('/').text)
        self.assertFalse(c.get('/admin/state').json()['configured'])
        self.assertEqual(c.get('/admin/overview').status_code,401)
        self.assertEqual(c.post('/admin/setup',json={'password':'short'}).status_code,422)
        self.assertEqual(c.post('/admin/setup',json={'name':'집 NAS','password':'테스트-password-123'}).status_code,200)
        self.assertTrue(c.get('/admin/state').json()['configured'])
        self.assertEqual(c.post('/admin/setup',json={'password':'another-password'}).status_code,409)
        cookie=c.cookies.get('gallery_admin');self.assertTrue(cookie)
        self.assertEqual(c.get('/admin/overview').json()['name'],'집 NAS')
        self.assertEqual(c.post('/admin/settings',headers={'Origin':'http://foreign.example'},json={'name':'bad'}).status_code,403)
        pair=c.post('/pair',json={'secret':'테스트-password-123','name':'PC'}).json()
        headers={'Authorization':'Bearer '+pair['token']}
        self.assertEqual(c.get('/devices',headers=headers).status_code,200)
        c.post('/admin/devices/'+pair['id']+'/rename',json={'name':'내 PC'})
        self.assertEqual(c.get('/admin/overview').json()['devices'][0]['name'],'내 PC')
        c.post('/admin/settings',json={'name':'새 이름'})
        c.post('/admin/logout',json={});self.assertEqual(c.get('/admin/overview').status_code,401)
        self.assertEqual(c.post('/admin/login',json={'password':'bad'}).status_code,403)
        self.assertEqual(c.post('/admin/login',json={'password':'테스트-password-123'}).status_code,200)
        c.post('/admin/password',json={'password':'새-password-456'})
        self.assertEqual(c.get('/admin/overview').status_code,401)
        self.assertEqual(c.get('/devices',headers=headers).status_code,200)
        self.assertEqual(c.post('/pair',json={'secret':'테스트-password-123','name':'new'}).status_code,403)
        self.assertEqual(c.post('/admin/login',json={'password':'새-password-456'}).status_code,200)
        c.post('/admin/devices/'+pair['id']+'/disconnect',json={})
        self.assertEqual(c.get('/devices',headers=headers).status_code,401)
        self.process.terminate();self.process.wait(timeout=10);self.start(self.port)
        self.assertEqual(c.get('/admin/overview').json()['name'],'새 이름')
        self.assertEqual(c.post('/pair',json={'secret':'새-password-456','name':'폰'}).status_code,200)
        database=(Path(self.temp.name)/'catalog.sqlite3').read_bytes()
        self.assertNotIn('새-password-456'.encode(),database)
        self.assertNotIn('테스트-password-123'.encode(),database)

if __name__=='__main__':unittest.main(verbosity=2)
