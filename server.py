"""LumiGo demo server. Python 3.10+, standard library; qrcode optional for PNG."""
import base64, hashlib, hmac, io, json, os, secrets, sqlite3, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('LUMIGO_DB',str(ROOT/'lumigo.sqlite3')))
LOCK=threading.RLock()
PORT=int(os.environ.get('PORT','8080'))
HOST=os.environ.get('HOST','127.0.0.1')
# This application is a demonstration: publicly accessible deployments must
# be gated by an explicitly configured private access key.
GATE_USER=os.environ.get('LUMIGO_GATE_USER','')
GATE_PASSWORD=os.environ.get('LUMIGO_GATE_PASSWORD','')

def connect():
 c=sqlite3.connect(DB,timeout=10); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA journal_mode=WAL'); return c

def pwd(password,salt=None):
 salt=salt or secrets.token_hex(16)
 return salt+'$'+hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),240000).hex()

def verify(password,encoded):
 try: salt,_=encoded.split('$',1); return hmac.compare_digest(pwd(password,salt),encoded)
 except: return False

def init():
 with connect() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,passhash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('user','merchant','operator','admin')),points INTEGER NOT NULL DEFAULT 0 CHECK(points>=0),created INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS sessions(tokenhash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires INTEGER NOT NULL,FOREIGN KEY(user_id) REFERENCES accounts(id));
  CREATE TABLE IF NOT EXISTS stores(id INTEGER PRIMARY KEY,name TEXT NOT NULL,owner INTEGER NOT NULL UNIQUE,active INTEGER NOT NULL DEFAULT 1,FOREIGN KEY(owner) REFERENCES accounts(id));
  CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,store_id INTEGER NOT NULL,name TEXT NOT NULL,price INTEGER NOT NULL CHECK(price>0),stock INTEGER NOT NULL CHECK(stock>=0),icon TEXT NOT NULL DEFAULT '🛍️',FOREIGN KEY(store_id) REFERENCES stores(id));
  CREATE TABLE IF NOT EXISTS charges(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL,store_id INTEGER NOT NULL,amount INTEGER NOT NULL CHECK(amount>0),state TEXT NOT NULL DEFAULT 'pending',payer INTEGER,created INTEGER NOT NULL,paid INTEGER,FOREIGN KEY(store_id) REFERENCES stores(id));
  CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL,delta INTEGER NOT NULL,kind TEXT NOT NULL,reference TEXT NOT NULL,created INTEGER NOT NULL,FOREIGN KEY(account_id) REFERENCES accounts(id));
  CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL,store_id INTEGER NOT NULL,product_id INTEGER NOT NULL,amount INTEGER NOT NULL,created INTEGER NOT NULL);
  ''')
  if not c.execute('SELECT 1 FROM accounts LIMIT 1').fetchone():
   demo=[('Valentina Gómez','usuario@lumigo.demo',os.environ.get('LUMIGO_USER_PASSWORD') or secrets.token_urlsafe(32),'user',45000),('Carlos Rojas','carlos@lumigo.demo',os.environ.get('LUMIGO_USER_PASSWORD') or secrets.token_urlsafe(32),'user',12500),('Comercio Café Andino','comercio@lumigo.demo',os.environ.get('LUMIGO_MERCHANT_PASSWORD') or secrets.token_urlsafe(32),'merchant',0),('LumiGo Operador','operador@lumigo.demo',os.environ.get('LUMIGO_OPERATOR_PASSWORD') or secrets.token_urlsafe(32),'operator',0),('LumiGo Administrador','admin@lumigo.demo',os.environ.get('LUMIGO_ADMIN_PASSWORD') or secrets.token_urlsafe(32),'admin',0)]
   for name,email,password,role,points in demo: c.execute('INSERT INTO accounts(name,email,passhash,role,points,created) VALUES(?,?,?,?,?,?)',(name,email,pwd(password),role,points,int(time.time())))
   owner=c.execute("SELECT id FROM accounts WHERE email='comercio@lumigo.demo'").fetchone()[0]
   c.execute('INSERT INTO stores(name,owner) VALUES(?,?)',('Café Andino',owner)); sid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
   for p in [('Capuchino',9500,30,'☕'),('Desayuno especial',18000,15,'🥐'),('Cuaderno premium',12000,10,'📘')]: c.execute('INSERT INTO products(store_id,name,price,stock,icon) VALUES(?,?,?,?,?)',(sid,*p))

class APIError(Exception):
 def __init__(self,msg,code=400): self.msg=msg; self.code=code

def need(cond,msg,code=400):
 if not cond: raise APIError(msg,code)

class Handler(BaseHTTPRequestHandler):
 def authorized_demo(self):
  # HTTPS-enabled private test deployment. Browser's Basic Auth challenge
  # blocks all application routes before demo accounts are accessible.
  if urlparse(self.path).path == '/api/health': return True
  cookie_name='lumigo_demo_gate'
  cookie=self.headers.get('Cookie','')
  expected=hmac.new(GATE_PASSWORD.encode(),b'lumigo-private-gate-v1',hashlib.sha256).hexdigest()
  for item in cookie.split(';'):
   name, _, value=item.strip().partition('=')
   if name==cookie_name and hmac.compare_digest(value,expected): return True
  auth=self.headers.get('Authorization','')
  if not auth.startswith('Basic '): return False
  try:
   raw=base64.b64decode(auth[6:],validate=True).decode('utf-8')
   username, password=raw.split(':',1)
   valid=hmac.compare_digest(username,GATE_USER) and hmac.compare_digest(password,GATE_PASSWORD)
   if valid: self._issue_demo_cookie=expected
   return valid
  except (ValueError,UnicodeError): return False
 def deny_gate(self):
  self.send_response(401)
  self.send_header('WWW-Authenticate','Basic realm="LumiGo demo privado", charset="UTF-8"')
  self.send_header('Cache-Control','no-store')
  self.send_header('Content-Length','0')
  self.end_headers()
 def log_message(self, fmt,*args): print('%s %s'%(self.address_string(),fmt%args))
 def send(self,obj,status=200,ctype='application/json; charset=utf-8'):
  data=json.dumps(obj,ensure_ascii=False).encode() if ctype.startswith('application/json') else obj
  self.send_response(status)
  if getattr(self,'_issue_demo_cookie',None): self.send_header('Set-Cookie','lumigo_demo_gate='+self._issue_demo_cookie+'; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=28800')
  self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY'); self.end_headers(); self.wfile.write(data)
 def body(self):
  n=int(self.headers.get('Content-Length','0')); need(0<n<=20000,'Solicitud inválida')
  try: val=json.loads(self.rfile.read(n)); need(isinstance(val,dict),'Objeto JSON requerido'); return val
  except (ValueError,UnicodeError): raise APIError('JSON inválido')
 def current(self,c):
  auth=self.headers.get('Authorization','')
  need(auth.startswith('Bearer '),'Inicia sesión',401)
  key=hashlib.sha256(auth[7:].encode()).hexdigest()
  row=c.execute('SELECT a.* FROM sessions s JOIN accounts a ON a.id=s.user_id WHERE s.tokenhash=? AND s.expires>?',(key,int(time.time()))).fetchone()
  need(row is not None,'Sesión caducada',401); return row
 def response(self,fn):
  try: fn()
  except APIError as e: self.send({'error':e.msg},e.code)
  except (sqlite3.Error,ValueError,TypeError) as e: self.send({'error':'No se pudo procesar la solicitud'},400)
 def do_GET(self):
  if not self.authorized_demo(): return self.deny_gate()
  self.response(self.get)
 def do_POST(self):
  if not self.authorized_demo(): return self.deny_gate()
  self.response(self.post)
 def get(self):
  route=urlparse(self.path).path
  if route=='/' or route=='/index.html': return self.send((ROOT/'public/index.html').read_bytes(),200,'text/html; charset=utf-8')
  if route=='/manifest.json': return self.send((ROOT/'public/manifest.json').read_bytes(),200,'application/manifest+json')
  if route=='/api/health': return self.send({'ok':True,'mode':'DEMO','payments_real':False})
  if route.startswith('/api/qr/'):
   code=route.split('/')[-1]
   with connect() as c: row=c.execute('SELECT code FROM charges WHERE code=?',(code,)).fetchone()
   need(row is not None,'QR inexistente',404)
   try:
    import qrcode
    im=qrcode.make('LUMIGO-DEMO:'+code); bio=io.BytesIO(); im.save(bio,format='PNG'); return self.send(bio.getvalue(),200,'image/png')
   except ImportError: raise APIError('Instala qrcode y pillow para generar QR PNG')
  with connect() as c:
   u=self.current(c)
   if route=='/api/me': return self.send({'id':u['id'],'name':u['name'],'email':u['email'],'role':u['role'],'points':u['points']})
   if route=='/api/lookup':
    code=parse_qs(urlparse(self.path).query).get('code',[''])[0].strip().upper()
    r=c.execute('SELECT q.code,q.amount,q.state,s.name AS store_name FROM charges q JOIN stores s ON s.id=q.store_id WHERE q.code=? AND s.active=1',(code,)).fetchone()
    need(r is not None,'Cobro inexistente',404)
    return self.send({'charge':dict(r)})
   if route=='/api/products': return self.send({'items':[dict(x) for x in c.execute('SELECT p.*,s.name AS store_name FROM products p JOIN stores s ON s.id=p.store_id WHERE s.active=1 ORDER BY p.id DESC')]})
   if route=='/api/stores': return self.send({'items':[dict(x) for x in c.execute('SELECT id,name,active FROM stores ORDER BY id')]})
   if route=='/api/movements': return self.send({'items':[dict(x) for x in c.execute('SELECT id,delta,kind,reference,created FROM movements WHERE account_id=? ORDER BY id DESC LIMIT 100',(u['id'],))]})
   if route=='/api/charges':
    if u['role']=='merchant': rows=c.execute('SELECT q.*,s.name store_name,a.name payer_name FROM charges q JOIN stores s ON s.id=q.store_id LEFT JOIN accounts a ON a.id=q.payer WHERE s.owner=? ORDER BY q.id DESC',(u['id'],))
    elif u['role'] in ('operator','admin'): rows=c.execute('SELECT q.*,s.name store_name,a.name payer_name FROM charges q JOIN stores s ON s.id=q.store_id LEFT JOIN accounts a ON a.id=q.payer ORDER BY q.id DESC LIMIT 100')
    else: rows=c.execute('SELECT q.*,s.name store_name FROM charges q JOIN stores s ON s.id=q.store_id WHERE q.payer=? ORDER BY q.id DESC',(u['id'],))
    return self.send({'items':[dict(x) for x in rows]})
   if route=='/api/dashboard':
    need(u['role'] in ('admin','operator'),'Sin permiso',403)
    return self.send({'users':c.execute("SELECT count(*) FROM accounts WHERE role='user'").fetchone()[0],'stores':c.execute('SELECT count(*) FROM stores').fetchone()[0],'recharges':c.execute("SELECT coalesce(sum(delta),0) FROM movements WHERE kind='recarga-demo'").fetchone()[0],'qr_paid':c.execute("SELECT count(*) FROM charges WHERE state='paid'").fetchone()[0]})
  raise APIError('Ruta inexistente',404)
 def post(self):
  route=urlparse(self.path).path
  b=self.body()
  if route=='/api/login':
   email=str(b.get('email','')).strip().lower(); password=str(b.get('password',''))
   with LOCK,connect() as c:
    u=c.execute('SELECT * FROM accounts WHERE email=?',(email,)).fetchone()
    need(u is not None and verify(password,u['passhash']),'Credenciales incorrectas',401)
    token=secrets.token_urlsafe(40); c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],int(time.time())+86400))
   return self.send({'token':token})
  if route=='/api/register':
   name=str(b.get('name','')).strip(); email=str(b.get('email','')).strip().lower(); password=str(b.get('password',''))
   need(2<=len(name)<=80 and '@' in email and len(email)<150 and len(password)>=10,'Revisa nombre, correo o contraseña (mínimo 10 caracteres)')
   with LOCK,connect() as c:
    need(not c.execute('SELECT 1 FROM accounts WHERE email=?',(email,)).fetchone(),'Correo ya registrado',409)
    c.execute('INSERT INTO accounts(name,email,passhash,role,points,created) VALUES(?,?,?,?,0,?)',(name,email,pwd(password),'user',int(time.time())))
   return self.send({'ok':True})
  with LOCK,connect() as c:
   c.execute('BEGIN IMMEDIATE')
   u=self.current(c)
   if route=='/api/logout':
    tokenhash=hashlib.sha256(self.headers['Authorization'][7:].encode()).hexdigest(); c.execute('DELETE FROM sessions WHERE tokenhash=?',(tokenhash,)); return self.send({'ok':True})
   if route=='/api/recharge-demo':
    need(u['role']=='user','Solo usuario',403)
    amount=b.get('amount'); need(type(amount)==int and 10000<=amount<=500000,'Monto entre $10.000 y $500.000')
    method=str(b.get('method','Nequi')); need(method in ('Nequi','DaviPlata','PSE','Tarjeta'),'Medio inválido')
    ref='DEMO-'+secrets.token_hex(6).upper()
    c.execute('UPDATE accounts SET points=points+? WHERE id=?',(amount,u['id']))
    c.execute('INSERT INTO movements(account_id,delta,kind,reference,created) VALUES(?,?,?,?,?)',(u['id'],amount,'recarga-demo',ref+' / '+method,int(time.time())))
    return self.send({'ok':True,'ref':ref,'message':'Recarga SIMULADA registrada; no hubo cobro bancario'})
   if route=='/api/charge':
    need(u['role']=='merchant','Solo comercios',403)
    amount=b.get('amount'); need(type(amount)==int and 100<=amount<=2000000,'Monto entre 100 y 2.000.000')
    s=c.execute('SELECT * FROM stores WHERE owner=? AND active=1',(u['id'],)).fetchone();need(s is not None,'Comercio no habilitado',403)
    code='LG-'+secrets.token_hex(7).upper();c.execute('INSERT INTO charges(code,store_id,amount,created) VALUES(?,?,?,?)',(code,s['id'],amount,int(time.time())))
    return self.send({'ok':True,'code':code})
   if route=='/api/pay-qr':
    need(u['role']=='user','Solo usuario',403)
    code=str(b.get('code','')).strip().upper().replace('LUMIGO-DEMO:','')
    q=c.execute('SELECT q.*,s.active FROM charges q JOIN stores s ON s.id=q.store_id WHERE q.code=?',(code,)).fetchone()
    need(q is not None,'Cobro inexistente',404);need(q['state']=='pending','Cobro ya procesado',409);need(q['active']==1,'Comercio suspendido',403)
    result=c.execute('UPDATE accounts SET points=points-? WHERE id=? AND points>=?',(q['amount'],u['id'],q['amount']))
    need(result.rowcount==1,'Saldo insuficiente',409)
    result=c.execute("UPDATE charges SET state='paid',payer=?,paid=? WHERE id=? AND state='pending'",(u['id'],int(time.time()),q['id']))
    need(result.rowcount==1,'Cobro ya procesado',409)
    c.execute('INSERT INTO movements(account_id,delta,kind,reference,created) VALUES(?,?,?,?,?)',(u['id'],-q['amount'],'pago-qr-demo',code,int(time.time())))
    return self.send({'ok':True,'code':code,'amount':q['amount']})
   if route=='/api/buy':
    need(u['role']=='user','Solo usuario',403);pid=b.get('product_id');need(type(pid)==int,'Producto inválido')
    p=c.execute('SELECT p.*,s.active FROM products p JOIN stores s ON s.id=p.store_id WHERE p.id=?',(pid,)).fetchone()
    need(p is not None and p['active']==1,'Producto no disponible',404)
    need(c.execute('UPDATE products SET stock=stock-1 WHERE id=? AND stock>0',(pid,)).rowcount==1,'Sin inventario',409)
    need(c.execute('UPDATE accounts SET points=points-? WHERE id=? AND points>=?',(p['price'],u['id'],p['price'])).rowcount==1,'Saldo insuficiente',409)
    ref='BUY-'+secrets.token_hex(6).upper(); c.execute('INSERT INTO purchases(account_id,store_id,product_id,amount,created) VALUES(?,?,?,?,?)',(u['id'],p['store_id'],pid,p['price'],int(time.time())))
    c.execute('INSERT INTO movements(account_id,delta,kind,reference,created) VALUES(?,?,?,?,?)',(u['id'],-p['price'],'compra-demo',ref,int(time.time())))
    return self.send({'ok':True,'ref':ref})
   if route=='/api/product':
    need(u['role']=='merchant','Solo comercio',403)
    s=c.execute('SELECT id FROM stores WHERE owner=?',(u['id'],)).fetchone();need(s is not None,'Comercio sin perfil',403)
    name=str(b.get('name','')).strip();price=b.get('price');stock=b.get('stock')
    need(2<=len(name)<=80 and type(price)==int and 100<=price<=10000000 and type(stock)==int and 0<=stock<=100000,'Producto inválido')
    c.execute('INSERT INTO products(store_id,name,price,stock) VALUES(?,?,?,?)',(s['id'],name,price,stock));return self.send({'ok':True})
   if route=='/api/admin-store':
    need(u['role']=='admin','Solo administrador',403)
    store_id=b.get('store_id'); active=b.get('active')
    need(type(store_id)==int and type(active)==bool,'Parámetros inválidos')
    need(c.execute('UPDATE stores SET active=? WHERE id=?',(int(active),store_id)).rowcount==1,'No existe comercio',404)
    return self.send({'ok':True})
  raise APIError('Ruta inexistente',404)

if __name__=='__main__':
 if not GATE_USER or len(GATE_PASSWORD)<24:
  raise SystemExit('Configura LUMIGO_GATE_USER y LUMIGO_GATE_PASSWORD (min. 24 caracteres) antes de exponer la demo.')
 init()
 print('LumiGo DEMO privado: operaciones simuladas',flush=True)
 ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
