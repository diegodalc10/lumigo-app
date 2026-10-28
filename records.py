"""Scoped immutable transaction reports and non-destructive view resets."""
import sqlite3
import tempfile
from pathlib import Path


def view_cutoff(c, user):
    row=c.execute('SELECT cutoff FROM report_markers WHERE account_id=?',(user['id'],)).fetchone()
    return row['cutoff'] if row else 0


def transaction_records(c,user,include_archived=False):
    staff=user['role'] in ('admin','operator')
    args=() if staff else (user['id'],)
    where='' if staff else ' AND s.owner=?' if user['role']=='merchant' else ' AND p.account_id=?'
    cutoff=0 if staff or include_archived else view_cutoff(c,user)
    purchases=[dict(r) for r in c.execute('SELECT p.id,p.created AS timestamp,p.amount,p.account_id,coalesce(p.reference,\'BUY-LEGACY-\'||p.id) AS reference,coalesce(p.product_name,pr.name) AS product,coalesce(p.store_name,s.name) AS store,a.name AS customer FROM purchases p JOIN stores s ON s.id=p.store_id JOIN products pr ON pr.id=p.product_id JOIN accounts a ON a.id=p.account_id WHERE p.created>=?'+where,(cutoff,*args))]
    where='' if staff else ' AND s.owner=?' if user['role']=='merchant' else ' AND q.payer=?'
    charges=[dict(r) for r in c.execute("SELECT q.id,q.paid AS timestamp,q.amount,q.payer AS account_id,q.code AS reference,'Pago QR' AS product,s.name AS store,a.name AS customer FROM charges q JOIN stores s ON s.id=q.store_id JOIN accounts a ON a.id=q.payer WHERE q.state='paid' AND q.paid>=?"+where,(cutoff,*args))]
    for row in purchases: row['type']='Compra de producto'
    for row in charges: row['type']='Pago QR'
    return sorted(purchases+charges,key=lambda r:(r['timestamp'],r['id']),reverse=True)


def export_products(c,user):
    if user['role']=='merchant': where,args=' WHERE s.owner=?',(user['id'],)
    elif user['role'] in ('admin','operator'): where,args='',()
    else: where,args=' WHERE s.active=1',()
    return [dict(r) for r in c.execute('SELECT p.id,p.name,s.name AS store,p.price,p.stock FROM products p JOIN stores s ON s.id=p.store_id'+where+' ORDER BY s.name,p.id',args)]


def backup_bytes(c):
    # Native SQLite backup is transaction-consistent, including WAL contents.
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'lumigo-backup.sqlite3'
        target=sqlite3.connect(path)
        try:
            c.backup(target)
            target.execute('DELETE FROM sessions')
            target.commit()
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('No se pudo verificar el respaldo')
        finally:
            target.close()
        return path.read_bytes()
