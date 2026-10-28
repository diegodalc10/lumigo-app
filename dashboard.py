"""Read-only, role-scoped analytics for the simulated LumiGo ledger."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import time

BOGOTA = timezone(timedelta(hours=-5))


def build_dashboard(c, user, days=30, now=None):
    now = int(time.time()) if now is None else now
    today = datetime.fromtimestamp(now, BOGOTA).date()
    first = today - timedelta(days=days-1)
    cutoff = int(datetime.combine(first, datetime.min.time(), BOGOTA).timestamp())
    role = user['role']
    staff = role in ('admin', 'operator')
    uid = user['id']
    merchant = role == 'merchant'
    rows = lambda sql, args=(): [dict(r) for r in c.execute(sql, args)]
    scalar = lambda sql, args=(): c.execute(sql, args).fetchone()[0]
    movements = []
    if not merchant:
        clause, args = ('', ()) if staff else (' AND m.account_id=?', (uid,))
        movements = rows('SELECT m.*,a.name AS person FROM movements m JOIN accounts a ON a.id=m.account_id WHERE m.created BETWEEN ? AND ?'+clause, (cutoff, now, *args))
    scope, scope_args = ('', ()) if staff else (' AND s.owner=?', (uid,)) if merchant else (' AND q.payer=?', (uid,))
    paid = rows("SELECT q.*,s.name AS store_name,a.name AS person FROM charges q JOIN stores s ON s.id=q.store_id LEFT JOIN accounts a ON a.id=q.payer WHERE q.state='paid' AND q.paid BETWEEN ? AND ?"+scope, (cutoff, now, *scope_args))
    charge_scope, charge_args = ('', ()) if staff else (' AND s.owner=?', (uid,)) if merchant else (' AND q.payer=?', (uid,))
    charges = rows('SELECT q.*,s.name AS store_name FROM charges q JOIN stores s ON s.id=q.store_id WHERE q.created BETWEEN ? AND ?'+charge_scope, (cutoff, now, *charge_args))
    purchase_scope, purchase_args = ('', ()) if staff else (' AND s.owner=?', (uid,)) if merchant else (' AND p.account_id=?', (uid,))
    purchases = rows('SELECT p.*,s.name AS store_name,pr.name AS product_name,a.name AS person FROM purchases p JOIN stores s ON s.id=p.store_id JOIN products pr ON pr.id=p.product_id JOIN accounts a ON a.id=p.account_id WHERE p.created BETWEEN ? AND ?'+purchase_scope, (cutoff, now, *purchase_args))
    series = {str(first+timedelta(days=i)): [0, 0] for i in range(days)}
    def add(ts, index, amount):
        key = str(datetime.fromtimestamp(ts, BOGOTA).date())
        if key in series:
            series[key][index] += amount
    credits = sum(m['delta'] for m in movements if m['delta'] > 0)
    qr_total = sum(q['amount'] for q in paid)
    purchases_total = sum(p['amount'] for p in purchases)
    for m in movements:
        if m['delta'] > 0:
            add(m['created'], 0, m['delta'])
    for q in paid:
        add(q['paid'], 0 if merchant else 1, q['amount'])
    for p in purchases:
        add(p['created'], 1, p['amount'])
    metrics = []
    def metric(label, value, unit='count', hint='En el período'):
        metrics.append(dict(label=label, value=value, unit=unit, hint=hint))
    if staff:
        metric('Usuarios registrados', scalar("SELECT count(*) FROM accounts WHERE role='user'"), hint='Total actual')
        metric('Comercios activos', scalar('SELECT count(*) FROM stores WHERE active=1'), hint='Total actual')
        metric('Puntos recargados', credits, 'points')
        metric('Consumos simulados', qr_total+purchases_total, 'points')
        metric('Pagos QR', len(paid))
        metric('Usuarios nuevos', scalar("SELECT count(*) FROM accounts WHERE role='user' AND created BETWEEN ? AND ?", (cutoff, now)))
    elif merchant:
        metric('Ventas simuladas', qr_total+purchases_total, 'points')
        metric('Cobros QR pagados', len(paid))
        metric('Compras de productos', len(purchases))
        metric('QR pendientes', sum(q['state']=='pending' for q in charges), hint='Creados en el período')
        metric('Productos', scalar('SELECT count(*) FROM products p JOIN stores s ON s.id=p.store_id WHERE s.owner=?', (uid,)), hint='Catálogo actual')
        metric('Unidades disponibles', scalar('SELECT coalesce(sum(p.stock),0) FROM products p JOIN stores s ON s.id=p.store_id WHERE s.owner=?', (uid,)), hint='Inventario actual')
    else:
        metric('Mi saldo', user['points'], 'points', 'Saldo actual, incluye puntos iniciales')
        metric('Puntos recibidos', credits, 'points')
        metric('Puntos utilizados', qr_total+purchases_total, 'points')
        metric('Pagos QR', len(paid))
        metric('Compras realizadas', len(purchases))
        metric('Recargas', sum(m['delta']>0 for m in movements))
    if role == 'user':
        composition = [{'label':'Pagos QR', 'value':qr_total}, {'label':'Compras', 'value':purchases_total}]
        composition_title, composition_unit = '¿En qué usé mis puntos?', 'points'
    else:
        composition = [{'label':'Pagados', 'value':sum(q['state']=='paid' for q in charges)}, {'label':'Pendientes', 'value':sum(q['state']=='pending' for q in charges)}]
        composition_title, composition_unit = 'Estado de los QR creados', 'count'
    ranking = defaultdict(int)
    for p in purchases:
        ranking[p['product_name'] if merchant else p['store_name']] += p['amount']
    if not merchant:
        for q in paid:
            ranking[q['store_name']] += q['amount']
    recent = []
    if not merchant:
        for m in movements:
            recent.append(dict(timestamp=m['created'],label=m['kind'].replace('-demo','').replace('-',' ').capitalize(),detail=m['person'] if staff else m['reference'],amount=m['delta'],reference=m['reference']))
    else:
        for q in paid:
            recent.append(dict(timestamp=q['paid'],label='Venta QR',detail=q['person'] or 'Usuario',amount=q['amount'],reference=q['code']))
        for p in purchases:
            recent.append(dict(timestamp=p['created'],label='Venta de producto',detail=p['product_name'],amount=p['amount'],reference='Compra #'+str(p['id'])))
    extras = []
    if role == 'admin':
        extras = rows('SELECT name,starts_at,location FROM events WHERE starts_at>=? ORDER BY starts_at LIMIT 5', (datetime.fromtimestamp(now, BOGOTA).isoformat(),))
        extra_title = 'Próximos eventos'
    elif merchant:
        extras = rows('SELECT p.name,p.stock FROM products p JOIN stores s ON s.id=p.store_id WHERE s.owner=? AND p.stock<=5 ORDER BY p.stock,p.id LIMIT 5', (uid,))
        extra_title = 'Inventario por revisar'
    elif role == 'operator':
        extras = rows('SELECT name,created FROM accounts WHERE role=\'user\' ORDER BY created DESC,id DESC LIMIT 5')
        extra_title = 'Usuarios recientes'
    else:
        extras = []
        extra_title = 'Tu actividad'
    return dict(role=role, days=days, generated_at=now, metrics=metrics,
                series=[dict(date=k,first=v[0],second=v[1]) for k,v in series.items()],
                series_labels=['Ventas QR','Ventas de productos'] if merchant else ['Recargas','Consumos'],
                composition=composition,composition_title=composition_title,composition_unit=composition_unit,
                ranking=[dict(label=k,value=v) for k,v in sorted(ranking.items(),key=lambda x:x[1],reverse=True)[:5]],
                ranking_title='Productos más vendidos' if merchant else 'Comercios con más actividad' if staff else 'Mis comercios por consumo',
                recent=sorted(recent,key=lambda r:r['timestamp'],reverse=True)[:8],extras=extras,extra_title=extra_title)
