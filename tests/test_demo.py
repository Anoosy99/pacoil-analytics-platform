import os
import tempfile
os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import main as m

def auth(client,role):
    r=client.post('/api/login',json={'role':role,'password':'pacoil-demo'})
    assert r.status_code==200
    return {'Authorization':'Bearer '+r.json()['token']}

def test_permissions_and_export():
    with TestClient(m.app) as c:
        assert c.get('/api/dashboard').status_code==401
        assert c.post('/api/login',json={'role':'owner','password':'wrong'}).status_code==401
        for role,expected in [('owner',6),('technical',5),('supply',1)]:
            headers=auth(c,role)
            data=c.get('/api/dashboard',headers=headers).json()
            assert len(data['sources'])==expected
            export=c.get('/api/export',headers=headers).text
            if role=='technical': assert 'STOCK' not in export
            if role=='supply': assert 'F601' not in export
            if role!='owner': assert c.post('/api/sources/F601/pause',headers=headers,json={'paused':True}).status_code==403
        assert c.get('/').status_code==200
        assert c.get('/health').status_code==200

def test_pause_staleness_resume_and_idempotency():
    with TestClient(m.app) as c:
        headers=auth(c,'owner')
        assert c.post('/api/sources/F601/pause',headers=headers,json={'paused':True}).status_code==200
        with m.Session.begin() as db:
            db.query(m.Reading).filter(m.Reading.source=='F601').delete()
            db.add(m.Reading(source='F601',timestamp=int(m.time.time())-30,value=2.0))
        m.collect()
        get=lambda: next(s for s in c.get('/api/dashboard',headers=headers).json()['sources'] if s['source']=='F601')
        assert get()['status']=='delayed'
        c.post('/api/sources/F601/pause',headers=headers,json={'paused':False})
        m.collect()
        assert get()['status']=='current'
        with m.Session.begin() as db:
            record={'source':'F601','timestamp':123,'value':2.0}
            assert m.ingest(db,[record,record])==1
            try: m.ingest(db,[{'source':'F601','timestamp':124,'value':float('nan')}])
            except ValueError: pass
            else: raise AssertionError('Invalid values must be rejected')
        c.post('/api/logout',headers=headers)
        assert c.get('/api/dashboard',headers=headers).status_code==401

def test_report_permissions_and_filters():
    with TestClient(m.app) as c:
        tech=auth(c,'technical')
        assert c.get('/api/records?source=STOCK',headers=tech).status_code==403
        assert c.get('/api/export?source=STOCK',headers=tech).status_code==403
        assert c.get('/api/records?source=F601&start=200&end=100',headers=tech).status_code==422
        with m.Session.begin() as db:
            m.ingest(db,[{'source':'F601','timestamp':500,'value':2.5},{'source':'F601','timestamp':600,'value':2.6}])
        result=c.get('/api/records?source=F601&start=500&end=500',headers=tech).json()
        assert result['records']==[{'timestamp':500,'value':2.5}]
        exported=c.get('/api/export?source=F601&start=500&end=500',headers=tech).text
        assert '500,2.5' in exported and '600,2.6' not in exported
