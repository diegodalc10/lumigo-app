"""Integration checks against a temporary SQLite database; no external payments."""
import base64
import importlib.util
import json
import io
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from PIL import Image
import os
from pathlib import Path
import secrets
import tempfile
import sys
import threading
import unittest
import urllib.error
import urllib.request


class StaffFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.saved_env = dict(os.environ)
        cls.passwords = {role: secrets.token_urlsafe(32) for role in ('USER', 'ADMIN', 'OPERATOR', 'MERCHANT')}
        os.environ.update({f'LUMIGO_{role}_PASSWORD': value for role, value in cls.passwords.items()})
        os.environ.update(LUMIGO_DB=cls.temp.name+'/test.sqlite3', LUMIGO_GATE_USER='test', LUMIGO_GATE_PASSWORD=secrets.token_urlsafe(32))
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        spec = importlib.util.spec_from_file_location('lumigo_test', Path(__file__).resolve().parents[1]/'server.py')
        cls.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app)
        cls.app.init()
        cls.app.Handler.log_message = lambda *args: None
        cls.server = cls.app.ThreadingHTTPServer(('127.0.0.1', 0), cls.app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:'+str(cls.server.server_port)
        auth = base64.b64encode(('test:'+os.environ['LUMIGO_GATE_PASSWORD']).encode()).decode()
        _, headers, _ = cls.request('/', headers={'Authorization': 'Basic '+auth})
        cls.cookie = headers['Set-Cookie'].split(';')[0]
        cls.sessions = {}
        for role, email in [('ADMIN','admin'), ('OPERATOR','operador'), ('USER','usuario'), ('MERCHANT','comercio')]:
            status, _, body = cls.request('/api/login', {'email':email+'@lumigo.demo','password':cls.passwords[role]}, {'Cookie':cls.cookie})
            assert status == 200
            cls.sessions[role] = {'Cookie':cls.cookie, 'Authorization':'Bearer '+body['token']}

    @classmethod
    def request(cls, path, data=None, headers=None):
        request = urllib.request.Request(cls.base+path, data=None if data is None else json.dumps(data).encode(), headers=headers or {})
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            body = json.loads(raw) if response.headers.get('Content-Type','').startswith('application/json') else raw
            return response.status, response.headers, body

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        os.environ.clear()
        os.environ.update(cls.saved_env)
        cls.temp.cleanup()

    def test_mobile_private_access_form(self):
        import http.client
        from urllib.parse import urlencode
        status,headers,page=self.request('/')
        self.assertEqual(status,200)
        self.assertNotIn('WWW-Authenticate',headers)
        self.assertIn(b'action="/private-access"',page)
        self.assertEqual(self.request('/api/products')[0],401)
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        for password,expected in [('wrong',401),(os.environ['LUMIGO_GATE_PASSWORD'],303)]:
            body=urlencode({'username':'test','password':password})
            conn.request('POST','/private-access',body,{'Content-Type':'application/x-www-form-urlencoded'})
            r=conn.getresponse();content=r.read()
            self.assertEqual(r.status,expected)
            self.assertIsNone(r.getheader('WWW-Authenticate'))
            self.assertNotIn(password.encode(),content)
            if expected==303:
                cookie=r.getheader('Set-Cookie')
                self.assertIn('Secure; HttpOnly; SameSite=Lax',cookie)
                self.assertEqual(r.getheader('Location'),'/')
                self.assertEqual(self.request('/',headers={'Cookie':cookie.split(';')[0]})[0],200)
        conn.close()

    def test_reports_preserve_purchase_name_price_and_reset_only_view(self):
        product=self.request('/api/manage-products',headers=self.sessions['MERCHANT'])[2]['items'][0]
        purchase=self.request('/api/buy',{'product_id':product['id']},self.sessions['USER'])
        self.assertEqual(purchase[0],200)
        products=self.request('/api/manage-products',headers=self.sessions['MERCHANT'])[2]['items']
        current=next(p for p in products if p['id']==product['id'])
        edit={'product_id':current['id'],'name':'Nuevo nombre después de compra','stock':current['stock'],'expected_stock':current['stock'],'price':current['price']+500,'expected_price':current['price']}
        self.assertEqual(self.request('/api/product-update',edit,self.sessions['MERCHANT'])[0],200)
        self.assertEqual(self.request('/api/product-update',edit,self.sessions['MERCHANT'])[0],409)
        records=self.request('/api/records?all=1',headers=self.sessions['USER'])[2]['items']
        original=next(r for r in records if r['reference']==purchase[2]['ref'])
        self.assertEqual(original['amount'],product['price'])
        self.assertEqual(original['product'],product['name'])
        merchant=self.request('/api/me',headers=self.sessions['MERCHANT'])[2]
        data={'target_id':merchant['id'],'confirmation':'REINICIAR VISTA','request_id':secrets.token_urlsafe(24)}
        self.assertEqual(self.request('/api/reset-view',data,self.sessions['USER'])[0],403)
        self.assertEqual(self.request('/api/reset-view',data,self.sessions['OPERATOR'])[0],403)
        self.assertEqual(self.request('/api/reset-view',dict(data,confirmation='no'),self.sessions['MERCHANT'])[0],400)
        self.assertEqual(self.request('/api/reset-view',data,self.sessions['MERCHANT'])[0],200)
        self.assertEqual(self.request('/api/records',headers=self.sessions['MERCHANT'])[2]['items'],[])
        full=self.request('/api/records?all=1',headers=self.sessions['MERCHANT'])[2]['items']
        self.assertTrue(any(r['reference']==purchase[2]['ref'] for r in full))
        self.assertTrue(self.request('/api/reset-view',data,self.sessions['MERCHANT'])[2]['replayed'])
        # Purchases after the reset are visible even within the same second.
        after=self.request('/api/buy',{'product_id':product['id']},self.sessions['USER'])
        self.assertEqual(after[0],200)
        visible=self.request('/api/records',headers=self.sessions['MERCHANT'])[2]['items']
        self.assertTrue(any(r['reference']==after[2]['ref'] for r in visible))
        self.assertFalse(any(r['reference']==purchase[2]['ref'] for r in visible))
        self.assertEqual(self.request('/api/reset-view',dict(data,target_id=1,request_id=secrets.token_urlsafe(24)),self.sessions['MERCHANT'])[0],403)
        self.app.init()
        self.assertTrue(any(r['reference']==purchase[2]['ref'] for r in self.request('/api/records?all=1',headers=self.sessions['USER'])[2]['items']))

    def test_excel_and_native_backup(self):
        for role in ('ADMIN','MERCHANT','USER'):
            status,headers,data=self.request('/api/export.xlsx?days=7',headers=self.sessions[role])
            self.assertEqual(status,200)
            self.assertIn('.xlsx',headers['Content-Disposition'])
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for name in archive.namelist():
                    if name.endswith('.xml') or name.endswith('.rels'): ET.fromstring(archive.read(name))
                self.assertIn('xl/charts/chart1.xml',archive.namelist())
                self.assertIn('xl/charts/chart2.xml',archive.namelist())
        self.assertEqual(self.request('/api/backup',headers=self.sessions['MERCHANT'])[0],403)
        backup=self.request('/api/backup',headers=self.sessions['ADMIN'])
        self.assertEqual(backup[0],200)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'backup.sqlite3';path.write_bytes(backup[2])
            with sqlite3.connect(path) as restored:
                self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(restored.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
                with self.app.connect() as live:
                    self.assertEqual(restored.execute('SELECT count(*) FROM accounts').fetchone()[0],live.execute('SELECT count(*) FROM accounts').fetchone()[0])

    def image_payload(self):
        stream=io.BytesIO()
        Image.new('RGB',(30,20),'blue').save(stream,format='PNG')
        return base64.b64encode(stream.getvalue()).decode()

    def test_product_images_permissions_and_inventory_conflict(self):
        product=self.request('/api/manage-products',headers=self.sessions['MERCHANT'])[2]['items'][0]
        payload={'kind':'product','target_id':product['id'],'data':self.image_payload()}
        self.assertEqual(self.request('/api/media-upload',payload,self.sessions['USER'])[0],403)
        self.assertEqual(self.request('/api/media-upload',payload,self.sessions['OPERATOR'])[0],403)
        status,_,photo=self.request('/api/media-upload',payload,self.sessions['MERCHANT'])
        self.assertEqual(status,201)
        image=self.request(photo['url'],headers=self.sessions['USER'])
        self.assertEqual(image[0],200)
        self.assertEqual(image[1]['Content-Type'],'image/jpeg')
        self.assertEqual(Image.open(io.BytesIO(image[2])).format,'JPEG')
        self.assertEqual(self.request(photo['url'])[0],401)
        self.assertEqual(self.request('/api/media-upload',dict(payload,data='not base64'),self.sessions['ADMIN'])[0],400)
        self.assertEqual(self.request(photo['url'],headers=self.sessions['USER'])[0],200)
        replacement=self.request('/api/media-upload',payload,self.sessions['ADMIN'])
        self.assertEqual(replacement[0],201)
        self.assertEqual(self.request(photo['url'],headers=self.sessions['USER'])[0],404)
        data={'product_id':product['id'],'name':'Producto actualizado','stock':12,'expected_stock':product['stock']}
        self.assertEqual(self.request('/api/product-update',data,self.sessions['USER'])[0],403)
        self.assertEqual(self.request('/api/product-update',dict(data,stock=-1),self.sessions['MERCHANT'])[0],400)
        self.assertEqual(self.request('/api/product-update',data,self.sessions['MERCHANT'])[0],200)
        self.assertEqual(self.request('/api/product-update',dict(data,expected_stock=-1),self.sessions['MERCHANT'])[0],409)
        updated=next(p for p in self.request('/api/manage-products',headers=self.sessions['MERCHANT'])[2]['items'] if p['id']==product['id'])
        self.assertEqual((updated['name'],updated['stock']),('Producto actualizado',12))
        self.assertEqual(updated['image_url'],replacement[2]['url'])
        self.assertEqual(self.request('/api/media-delete',{'image_id':replacement[2]['id']},self.sessions['USER'])[0],403)
        self.assertEqual(self.request('/api/media-delete',{'image_id':replacement[2]['id']},self.sessions['MERCHANT'])[0],200)

    def test_avatar_private_cookie_and_gallery_limit(self):
        status,_,photo=self.request('/api/media-upload',{'kind':'avatar','data':self.image_payload(),'target_id':999999},self.sessions['USER'])
        self.assertEqual(status,201)
        self.assertEqual(self.request(photo['url'],headers=self.sessions['ADMIN'])[0],403)
        self.assertEqual(self.request(photo['url'],headers=self.sessions['USER'])[0],200)
        status,headers,me=self.request('/api/me',headers=self.sessions['USER'])
        self.assertEqual(me['photo_url'],photo['url'])
        self.assertIn('HttpOnly',headers['Set-Cookie'])
        self.assertIn('Secure',headers['Set-Cookie'])
        media_cookie=self.cookie+'; '+headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request(photo['url'],headers={'Cookie':media_cookie})[0],200)
        # Cookie-only media access cannot authorize mutations.
        self.assertEqual(self.request('/api/media-upload',{'kind':'avatar','data':self.image_payload()}, {'Cookie':media_cookie})[0],401)
        store=self.request('/api/my-store',headers=self.sessions['MERCHANT'])[2]['store']
        data={'kind':'store','target_id':store['id'],'data':self.image_payload()}
        self.assertEqual(self.request('/api/media-upload',data,self.sessions['USER'])[0],403)
        ids=[]
        for _ in range(6):
            status,_,result=self.request('/api/media-upload',data,self.sessions['MERCHANT'])
            self.assertEqual(status,201)
            ids.append(result['id'])
        self.assertEqual(self.request('/api/media-upload',data,self.sessions['MERCHANT'])[0],409)
        self.assertEqual(self.request('/api/media-delete',{'image_id':ids[0]},self.sessions['MERCHANT'])[0],200)
        self.assertEqual(self.request('/api/media-upload',data,self.sessions['MERCHANT'])[0],201)
        self.assertEqual(len(self.request('/api/my-store',headers=self.sessions['MERCHANT'])[2]['store']['images']),6)

    def test_other_merchant_cannot_modify_products_or_business(self):
        with self.app.connect() as c:
            password=secrets.token_urlsafe(24)
            uid=c.execute("INSERT INTO accounts(name,email,passhash,role,points,created) VALUES(?,?,?,'merchant',0,0)",('Other','othermerchant@demo',self.app.pwd(password))).lastrowid
            sid=c.execute('INSERT INTO stores(name,owner) VALUES(?,?)',('Other shop',uid)).lastrowid
            pid=c.execute('INSERT INTO products(store_id,name,price,stock) VALUES(?,?,?,?)',(sid,'Other product',1000,5)).lastrowid
        data={'kind':'product','target_id':pid,'data':self.image_payload()}
        self.assertEqual(self.request('/api/media-upload',data,self.sessions['MERCHANT'])[0],403)
        self.assertEqual(self.request('/api/product-update',{'product_id':pid,'name':'Wrong','stock':0,'expected_stock':5},self.sessions['MERCHANT'])[0],403)
        self.assertEqual(self.request('/api/media-upload',dict(data,kind='store',target_id=sid),self.sessions['MERCHANT'])[0],403)
        managed=self.request('/api/manage-products',headers=self.sessions['MERCHANT'])[2]['items']
        self.assertNotIn(pid,[p['id'] for p in managed])

    def test_dashboard_routes_and_protected_assets(self):
        for role in self.sessions:
            status, _, result = self.request('/api/dashboard?days=7',headers=self.sessions[role])
            self.assertEqual(status,200)
            self.assertEqual(result['role'],{'USER':'user','MERCHANT':'merchant','ADMIN':'admin','OPERATOR':'operator'}[role])
            self.assertEqual(len(result['series']),7)
        self.assertEqual(self.request('/api/dashboard?days=365',headers=self.sessions['ADMIN'])[0],400)
        for path in ('/dashboard.js','/dashboard.css'):
            self.assertEqual(self.request(path)[0],401)
            self.assertEqual(self.request(path,headers={'Cookie':self.cookie})[0],200)

    def test_user_creation_and_privilege_boundaries(self):
        for role in ('ADMIN', 'OPERATOR'):
            data = {'name':'Usuario de prueba', 'email':role.lower()+'-created@lumigo.demo', 'password':secrets.token_urlsafe(24)}
            status, _, result = self.request('/api/staff-users', data, self.sessions[role])
            self.assertEqual(status, 201)
            self.assertEqual((result['user']['role'],result['user']['points']), ('user',0))
            self.assertNotIn(data['password'], json.dumps(result))
            self.assertEqual(self.request('/api/login', {'email':data['email'],'password':data['password']}, {'Cookie':self.cookie})[0],200)
            self.assertEqual(self.request('/api/staff-users', dict(data,email=data['email'].upper()), self.sessions[role])[0],409)
            self.assertEqual(self.request('/api/staff-users', dict(data,role='admin'), self.sessions[role])[0],403)
            self.assertEqual(self.request('/api/staff-users', dict(data,email='invalid'), self.sessions[role])[0],400)
        for role in ('USER','MERCHANT'):
            self.assertEqual(self.request('/api/staff-users', {}, self.sessions[role])[0],403)
            self.assertEqual(self.request('/api/staff-users', headers=self.sessions[role])[0],403)
        users = self.request('/api/staff-users',headers=self.sessions['OPERATOR'])[2]['items']
        self.assertTrue(all('passhash' not in user and 'password' not in user for user in users))

    def test_events_and_non_destructive_initialization(self):
        data = {'name':'Feria de prueba','starts_at':'2026-11-15T18:30','location':'Bogotá','description':'Evento simulado'}
        for role in ('OPERATOR','USER','MERCHANT'):
            self.assertEqual(self.request('/api/admin-events',data,self.sessions[role])[0],403)
            self.assertEqual(self.request('/api/admin-events',headers=self.sessions[role])[0],403)
        self.assertEqual(self.request('/api/admin-events',dict(data,starts_at='2026-02-30T10:00'),self.sessions['ADMIN'])[0],400)
        status, _, result = self.request('/api/admin-events',data,self.sessions['ADMIN'])
        self.assertEqual(status,201)
        self.app.init()
        events = self.request('/api/admin-events',headers=self.sessions['ADMIN'])[2]['items']
        event = next(e for e in events if e['id']==result['id'])
        self.assertEqual(event['starts_at'],'2026-11-15T18:30:00-05:00')

    def test_admin_recharge_is_audited_and_idempotent(self):
        users = self.request('/api/staff-users',headers=self.sessions['ADMIN'])[2]['items']
        target = next(u for u in users if u['email']=='usuario@lumigo.demo')
        data = {'account_id':target['id'],'amount':10000,'note':'Prueba','request_id':secrets.token_urlsafe(24)}
        for role in ('OPERATOR','USER','MERCHANT'):
            self.assertEqual(self.request('/api/admin-recharges',data,self.sessions[role])[0],403)
            self.assertEqual(self.request('/api/admin-recharges',headers=self.sessions[role])[0],403)
        for amount in (True, -1, 1, 500001, 10000.5, '10000'):
            self.assertEqual(self.request('/api/admin-recharges',dict(data,amount=amount),self.sessions['ADMIN'])[0],400)
        self.assertEqual(self.request('/api/admin-recharges',dict(data,account_id=999999),self.sessions['ADMIN'])[0],404)
        status, _, result = self.request('/api/admin-recharges',data,self.sessions['ADMIN'])
        self.assertEqual(status,201)
        replay = self.request('/api/admin-recharges',data,self.sessions['ADMIN'])
        self.assertEqual(replay[0],200)
        self.assertTrue(replay[2]['replayed'])
        self.assertEqual(self.request('/api/admin-recharges',dict(data,amount=20000),self.sessions['ADMIN'])[0],409)
        account = self.request('/api/me',headers=self.sessions['USER'])[2]
        self.assertEqual(account['points'],target['points']+10000)
        history = self.request('/api/movements',headers=self.sessions['USER'])[2]['items']
        self.assertEqual(len([m for m in history if m['reference']==result['ref']]),1)
        audit = self.request('/api/admin-recharges',headers=self.sessions['ADMIN'])[2]['items']
        self.assertEqual(audit[0]['reference'],result['ref'])
        self.assertEqual(audit[0]['email'],target['email'])
        self.assertTrue(audit[0]['actor_name'])
        self.assertFalse(self.request('/api/health')[2]['payments_real'])
        self.assertEqual(self.request('/api/admin-recharges',data)[0],401)


if __name__ == '__main__':
    unittest.main()
