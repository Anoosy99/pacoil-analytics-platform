"""Simulated data only. Single-process demo, not a plant control system."""
import asyncio, csv, io, math, os, secrets, time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, UniqueConstraint, select
from sqlalchemy.orm import declarative_base, sessionmaker
URL = os.getenv('DATABASE_URL', 'sqlite:///./demo.db')
engine = create_engine(URL, connect_args={'check_same_thread':False} if URL.startswith('sqlite') else {})
Session = sessionmaker(engine)
Base = declarative_base()
SOURCES = {'B602':('industrial','Temperature','°C',95), 'F601':('industrial','Pressure','bar',2.1), 'F602':('industrial','Pressure','bar',2.3), 'F603':('industrial','Pressure','bar',1.9), 'F604':('industrial','Pressure','bar',2), 'STOCK':('supply','Available stock','t',180)}
paused, sessions = set(), {}
last_error = None
class Reading(Base):
    __tablename__ = 'readings'
    id = Column(Integer,primary_key=True)
    source = Column(String,nullable=False)
    timestamp = Column(Integer,nullable=False)
    value = Column(Float,nullable=False)
    __table_args__ = (UniqueConstraint('source','timestamp'),)
class ImportRun(Base):
    __tablename__ = 'import_runs'
    id = Column(Integer,primary_key=True)
    timestamp = Column(Integer,nullable=False)
    count = Column(Integer,nullable=False)
def ingest(db, records):
    count = 0
    for r in records:
        if r['source'] not in SOURCES or not isinstance(r['timestamp'],int) or r['timestamp'] < 0 or not math.isfinite(r['value']):
            raise ValueError('Invalid record')
        if not db.scalar(select(Reading).where(Reading.source==r['source'],Reading.timestamp==r['timestamp'])):
            db.add(Reading(**r)); db.flush(); count += 1
    return count
def collect(stamp=None):
    stamp = int(time.time()) if stamp is None else stamp
    records = [{'source':s,'timestamp':stamp,'value':round(c[3]*(1+.04*math.sin(stamp/24+i)),2)} for i,(s,c) in enumerate(SOURCES.items()) if s not in paused]
    with Session.begin() as db:
        count = ingest(db,records)
        db.add(ImportRun(timestamp=stamp,count=count))
async def collector():
    global last_error
    while True:
        try:
            await asyncio.to_thread(collect)
            last_error = None
        except Exception:
            last_error = 'Collection failed; check server logs.'
            import logging
            logging.exception('Collection failed')
        await asyncio.sleep(5)
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with Session() as db:
        empty = db.scalar(select(Reading.id).limit(1)) is None
    if empty:
        now = int(time.time())
        for stamp in range(now-300,now,5): collect(stamp)
    task = asyncio.create_task(collector())
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
app = FastAPI(title='PACOIL simulated analytics',lifespan=lifespan)
ROOT = Path(__file__).parent
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
class Login(BaseModel):
    role:str
    password:str
@app.post('/api/login')
def login(body:Login):
    if body.role not in ('owner','technical','supply') or not secrets.compare_digest(body.password,os.getenv('DEMO_PASSWORD','pacoil-demo')):
        raise HTTPException(401,'Incorrect demo credentials')
    token = secrets.token_urlsafe(32)
    sessions[token] = (body.role,time.time()+28800)
    return {'token':token,'role':body.role}
def user(request:Request):
    token = request.headers.get('authorization','').removeprefix('Bearer ')
    session = sessions.get(token)
    if not session or session[1]<time.time():
        sessions.pop(token,None)
        raise HTTPException(401,'Please sign in')
    return session[0]
def allowed(role,source):
    return role=='owner' or SOURCES[source][0]=={'technical':'industrial','supply':'supply'}.get(role)
@app.post('/api/logout')
def logout(request:Request,role=Depends(user)):
    sessions.pop(request.headers.get('authorization','').removeprefix('Bearer '),None)
    return {'ok':True}
@app.get('/api/dashboard')
def dashboard(role=Depends(user)):
    now,items=int(time.time()),[]
    with Session() as db:
        for source,c in SOURCES.items():
            if not allowed(role,source): continue
            rows=list(reversed(db.scalars(select(Reading).where(Reading.source==source).order_by(Reading.timestamp.desc()).limit(60)).all()))
            latest=rows[-1] if rows else None
            age=now-latest.timestamp if latest else None
            items.append({'source':source,'department':c[0],'metric':c[1],'unit':c[2],'paused':source in paused,'value':latest.value if latest else None,'last_updated':latest.timestamp if latest else None,'age':age,'status':'delayed' if age is None or age>15 else 'current','average':round(sum(r.value for r in rows)/len(rows),2) if rows else None,'history':[{'timestamp':r.timestamp,'value':r.value} for r in rows]})
    return {'demo':True,'role':role,'updated_at':now,'collection_error':last_error,'sources':items}
class Pause(BaseModel):
    paused:bool
@app.post('/api/sources/{source}/pause')
def pause(source:str,body:Pause,role=Depends(user)):
    if role!='owner': raise HTTPException(403,'Only owner can change simulation settings')
    if source not in SOURCES: raise HTTPException(404,'Unknown source')
    paused.add(source) if body.paused else paused.discard(source)
    return {'source':source,'paused':source in paused}
@app.get('/api/export')
def export(role=Depends(user)):
    buf=io.StringIO(); writer=csv.writer(buf)
    writer.writerow(['source','timestamp_utc_epoch','value','unit','simulated'])
    with Session() as db:
        permitted=[s for s in SOURCES if allowed(role,s)]
        for r in db.scalars(select(Reading).where(Reading.source.in_(permitted)).order_by(Reading.timestamp.desc()).limit(10000)):
            writer.writerow([r.source,r.timestamp,r.value,SOURCES[r.source][2],'true'])
    return StreamingResponse(iter([buf.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="pacoil-demo.csv"'})
@app.get('/health')
def health():
    with Session() as db: db.execute(select(1))
    return {'status':'ok','mode':'simulated'}
@app.get('/')
def index(): return FileResponse(ROOT/'static'/'index.html')
