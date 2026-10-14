"""Validate the actual built Linux image through its published HTTP port."""
import sys
import time
import httpx

url=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8877'
with httpx.Client(base_url=url,headers={'X-Gallery-UI':'1','Origin':url},timeout=20) as client:
    for attempt in range(60):
        try:
            if client.get('/health',timeout=2).is_success:break
        except httpx.TransportError:pass
        time.sleep(.5)
    else:raise RuntimeError('Image did not start')
    assert 'NAS 서버를 시작' in client.get('/').text
    assert not client.get('/admin/state').json()['configured']
    client.post('/admin/setup',json={'name':'Container smoke test','password':'image-test-password'}).raise_for_status()
    assert client.get('/admin/overview').json()['name']=='Container smoke test'
    pair=client.post('/pair',json={'name':'Test device','secret':'image-test-password'})
    pair.raise_for_status()
    assert client.get('/admin/overview').json()['devices'][0]['name']=='Test device'
    client.post('/admin/logout',json={}).raise_for_status()
    assert client.get('/admin/overview').status_code==401
print('PASS actual image: web setup, persistent settings, admin session, device registration')
