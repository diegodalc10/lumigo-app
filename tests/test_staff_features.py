"""Integration checks against a temporary SQLite database; no external payments."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import secrets
import tempfile
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
