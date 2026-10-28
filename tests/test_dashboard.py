import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec = importlib.util.spec_from_file_location('dashboard', ROOT/'dashboard.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        # Use the production schema, not a second schema definition.
        source = (ROOT/'server.py').read_text()
        self.c.executescript(source.split("c.executescript('''",1)[1].split("''')",1)[0])
        self.now = int(datetime(2026,10,28,12,tzinfo=timezone(timedelta(hours=-5))).timestamp())
        for uid,role in [(1,'user'),(2,'user'),(3,'merchant'),(4,'merchant'),(5,'admin'),(6,'operator')]:
            self.c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?)',(uid,'Person '+str(uid),'test'+str(uid)+'@demo','hash',role,50000,self.now))
        self.c.executemany('INSERT INTO stores VALUES(?,?,?,1)',[(1,'Store A',3),(2,'Store B',4)])
        self.c.executemany('INSERT INTO products VALUES(?,?,?,?,?,?)',[(1,1,'Product A',2000,4,'x'),(2,2,'Product B',9000,20,'x')])
        self.c.execute('INSERT INTO events VALUES(1,?,?,?,?,?,?)',('Admin only event','2026-11-01T10:00:00-05:00','Bogotá','',5,self.now))
        self.c.executemany('INSERT INTO movements(account_id,delta,kind,reference,created) VALUES(?,?,?,?,?)',[(1,10000,'recarga-demo','credit-one',self.now),(2,80000,'recarga-demo','private-two',self.now),(1,-1000,'pago-qr-demo','QR-A',self.now),(2,-7000,'pago-qr-demo','QR-B',self.now),(1,-2000,'compra-demo','BUY-A',self.now)])
        self.c.executemany('INSERT INTO charges(code,store_id,amount,state,payer,created,paid) VALUES(?,?,?,?,?,?,?)',[('QR-A',1,1000,'paid',1,self.now,self.now),('QR-B',2,7000,'paid',2,self.now,self.now),('QR-P',1,500,'pending',None,self.now,None)])
        self.c.execute('INSERT INTO purchases(account_id,store_id,product_id,amount,created) VALUES(?,?,?,?,?)',(1,1,1,2000,self.now))

    def tearDown(self):
        self.c.close()

    def dashboard(self,uid,days=30):
        user=self.c.execute('SELECT * FROM accounts WHERE id=?',(uid,)).fetchone()
        return module.build_dashboard(self.c,user,days,self.now)

    def test_user_data_is_private_and_totals_match(self):
        d=self.dashboard(1)
        self.assertEqual(sum(p['first'] for p in d['series']),10000)
        self.assertEqual(sum(p['second'] for p in d['series']),3000)
        self.assertEqual(sum(p['value'] for p in d['composition']),3000)
        self.assertEqual(d['ranking'],[{'label':'Store A','value':3000}])
        text=json.dumps(d)
        for other in ['private-two','QR-B','Person 2','Store B','Admin only event','hash']:
            self.assertNotIn(other,text)
        self.assertEqual(d['metrics'][0]['value'],50000)

    def test_merchant_does_not_see_other_stores(self):
        d=self.dashboard(3)
        self.assertEqual(d['metrics'][0]['value'],3000)
        self.assertEqual(sum(p['first'] for p in d['series']),1000)
        self.assertEqual(sum(p['second'] for p in d['series']),2000)
        self.assertEqual([p['value'] for p in d['composition']],[1,1])
        self.assertEqual(d['ranking'],[{'label':'Product A','value':2000}])
        self.assertNotIn('Store B',json.dumps(d))
        self.assertNotIn('Product B',json.dumps(d))
        self.assertNotIn('private-two',json.dumps(d))
        self.assertEqual(d['extras'][0]['stock'],4)

    def test_staff_totals_do_not_double_count_payments(self):
        for uid in (5,6):
            d=self.dashboard(uid)
            self.assertEqual(sum(p['first'] for p in d['series']),90000)
            self.assertEqual(sum(p['second'] for p in d['series']),10000)
            self.assertEqual(d['metrics'][3]['value'],10000)
        self.assertEqual(self.dashboard(5)['extras'][0]['name'],'Admin only event')
        self.assertNotIn('Admin only event',json.dumps(self.dashboard(6)))

    def test_period_bounds_empty_days_and_bogota_midnight(self):
        old=self.now-10*86400
        self.c.execute('INSERT INTO movements(account_id,delta,kind,reference,created) VALUES(?,?,?,?,?)',(1,555,'recarga-demo','old',old))
        seven=self.dashboard(1,7)
        self.assertEqual(len(seven['series']),7)
        self.assertEqual(sum(p['first'] for p in seven['series']),10000)
        self.assertEqual(sum(p['first'] for p in self.dashboard(1,30)['series']),10555)
        # 04:30 UTC is still the previous calendar day in Bogotá.
        ts=int(datetime(2026,10,28,4,30,tzinfo=timezone.utc).timestamp())
        self.c.execute('INSERT INTO movements(account_id,delta,kind,reference,created) VALUES(?,?,?,?,?)',(1,123,'recarga-demo','night',ts))
        d=self.dashboard(1,7)
        self.assertEqual(next(p for p in d['series'] if p['date']=='2026-10-27')['first'],123)
        self.assertEqual(len(self.dashboard(1,90)['series']),90)
        empty=self.dashboard(4)
        self.assertEqual(empty['recent'][0]['reference'],'QR-B')
        self.c.execute('DELETE FROM charges WHERE store_id=2')
        empty=self.dashboard(4)
        self.assertEqual(empty['recent'],[])
        self.assertEqual(sum(p['first']+p['second'] for p in empty['series']),0)


if __name__=='__main__':
    unittest.main()
