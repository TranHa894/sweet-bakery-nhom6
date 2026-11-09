"""Một server FastAPI: cửa hàng + database SQLite + chatbot của nhóm."""
import hmac
import json
import os
import secrets
import sqlite3
import time
import unicodedata
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Request, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError
from starlette.staticfiles import StaticFiles

from database import ROOT, DB_PATH, initialize, connect, catalog
from app.storage import utc_now, fingerprint
from app.api import create_app as create_chatbot
from website_catalog import WebsiteCatalogRepository
from website_orders import Customer, Address, Delivery, Item, Order, OrderError, place_order, order_view, create_website_order_tools, delivery_info, read_order_updates, cancel_order
from website_delivery import DeliveryLocation, store_settings, estimate_delivery, delivery_message, delivery_now, in_delivery_hours, customer_delivery_window, delivery_dates_changed
from app import config as chat_config
from app.knowledge_loader import EmptyKnowledgeRepository

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Login(Model):
    password: str = Field(min_length=1,max_length=200)

class ProductUpdate(Model):
    price: int = Field(strict=True,ge=0,le=1_000_000_000)
    stock: int = Field(strict=True,ge=0,le=1_000_000)
    active: bool = Field(strict=True)
    expectedRevision: str = Field(pattern=r'^[0-9a-f]{64}$')


class Status(Model):
    status: Literal['confirmed','delivering','completed','cancelled']
    expectedArrival: datetime | None = None

    @field_validator('expectedArrival')
    @classmethod
    def valid_arrival(cls,value):
        if value and (value.tzinfo is None or value<=delivery_now()):
            raise ValueError('future_timezone_required')
        if value and not in_delivery_hours(value):
            raise PydanticCustomError('delivery_hours','Giờ nhận cần nằm trong 08:00–18:00 giờ Việt Nam.')
        return value


def create_app(db_path=DB_PATH, admin_password=None):
    sessions={}; attempts={}; lock=Lock(); password=admin_password

    @asynccontextmanager
    async def lifespan(app):
        nonlocal password
        initialize(db_path)
        if password is None:
            password=os.environ.get('SWEET_ADMIN_PASSWORD')
            if not password:
                password_path=ROOT/'runtime/admin-password.txt'
                password_path.parent.mkdir(parents=True,exist_ok=True)
                if not password_path.exists():password_path.write_text(secrets.token_urlsafe(12),encoding='utf-8')
                password=password_path.read_text(encoding='utf-8').strip()
        if not password:raise RuntimeError('Admin password must not be empty')
        print('\nSWEET BAKERY: http://127.0.0.1:8000\nQUAN LY: http://127.0.0.1:8000/admin.html\nMat khau: xem runtime/admin-password.txt (hoac SWEET_ADMIN_PASSWORD).\n')
        yield
        sessions.clear()

    app=FastAPI(title='Sweet Bakery — Nhóm 6',lifespan=lifespan)

    @app.middleware('http')
    async def protections(request,call_next):
        if request.method in {'POST','PATCH','DELETE','PUT'}:
            origin=request.headers.get('origin')
            if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'origin_not_allowed'},status_code=403)
        response=await call_next(request)
        if request.url.path.startswith(('/api','/chatbot/api')) or request.url.path in {'/','/chatbot/','/website/'} or request.url.path.endswith(('.html','.js','.css')):
            response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request,exc):
        return JSONResponse({'detail':'invalid_data','fields':[{'loc':list(e['loc']),'type':e['type']} for e in exc.errors()]},status_code=422)

    @app.exception_handler(sqlite3.Error)
    async def db_error(request,exc):
        return JSONResponse({'detail':'database_busy_or_unavailable'},status_code=503)

    def authorize(request):
        token=request.cookies.get('sweet_admin','')
        with lock:
            expiry=sessions.get(token,0)
            if expiry<time.monotonic():
                sessions.pop(token,None)
                raise HTTPException(401,'admin_login_required')

    @app.get('/api/health')
    def health():
        db=connect(db_path)
        try:db.execute('SELECT 1');return {'status':'ok','products':len(catalog(db_path)),'chatbot':'/chatbot/','environment':'local_coursework'}
        finally:db.close()

    @app.get('/api/store')
    def store_location():
        return {'store':store_settings()}

    @app.post('/api/delivery/estimate')
    def delivery_estimate(body:DeliveryLocation):
        return estimate_delivery(body.model_dump())

    @app.get('/api/products')
    def products():return catalog(db_path)

    @app.post('/api/orders')
    def submit(body:Order, response:Response, idempotency_key:str=Header(min_length=8,max_length=128)):
        db=connect(db_path)
        try:
            db.execute('BEGIN IMMEDIATE')
            result,created=place_order(db,body,idempotency_key)
            db.commit()
            response.status_code=201 if created else 200
            return result
        except OrderError as error:
            raise HTTPException(error.status_code,error.detail) from None
        finally:
            if db.in_transaction:db.rollback()
            db.close()

    @app.post('/api/admin/login')
    def login(body:Login,request:Request,response:Response):
        ip=request.client.host if request.client else 'local';now=time.monotonic()
        with lock:
            recent=[t for t in attempts.get(ip,[]) if now-t<60]
            if len(recent)>=10:raise HTTPException(429,'try_again_in_one_minute')
            if password is None or not hmac.compare_digest(body.password.encode('utf-8'),password.encode('utf-8')):
                attempts[ip]=recent+[now];raise HTTPException(401,'invalid_password')
            attempts.pop(ip,None)
            for key in list(sessions):
                if sessions[key]<now:sessions.pop(key)
            token=secrets.token_urlsafe(32);sessions[token]=now+8*60*60
        response.set_cookie('sweet_admin',token,httponly=True,samesite='strict',max_age=8*60*60,path='/api/admin')
        return {'ok':True}

    @app.post('/api/admin/logout')
    def logout(request:Request,response:Response):
        with lock:sessions.pop(request.cookies.get('sweet_admin',''),None)
        response.delete_cookie('sweet_admin',path='/api/admin');return {'ok':True}


    @app.get('/api/admin/orders')
    def orders(request:Request, q:str=Query(default='',max_length=100),
               status_filter:Literal['pending_confirmation','confirmed','delivering','completed','cancelled']|None=Query(default=None,alias='status'),
               date_from:date|None=Query(default=None,alias='dateFrom'),date_to:date|None=Query(default=None,alias='dateTo'),
               limit:int=Query(default=500,ge=1,le=500),offset:int=Query(default=0,ge=0),
               include_requests:bool=True):
        authorize(request)
        if date_from and date_to and date_from>date_to:raise HTTPException(422,'invalid_date_range')
        clauses=[];params=[]
        if q.strip():
            # INSTR coi %, _ và dấu nháy là văn bản, không phải mẫu LIKE hay SQL.
            clauses.append("instr(fold_text(id||' '||customer_name||' '||phone),fold_text(?))>0")
            params.append(q.strip())
        if status_filter:
            clauses.append("(CASE WHEN status='confirmed' AND EXISTS(SELECT 1 FROM web_delivery_updates d WHERE d.order_id=web_orders.id AND d.dispatched_at IS NOT NULL) THEN 'delivering' ELSE status END)=?");params.append(status_filter)
        for day,operator,delta in ((date_from,'>=',0),(date_to,'<',1)):
            if day:
                if day==date.max and delta:raise HTTPException(422,'invalid_date_range')
                try:
                    bound=datetime.combine(day+timedelta(days=delta),datetime.min.time(),tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
                    utc_bound=bound.astimezone(timezone.utc).isoformat()
                except (OverflowError,ValueError):
                    raise HTTPException(422,'invalid_date_range')
                clauses.append(f'created_at{operator}?');params.append(utc_bound)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        db=connect(db_path)
        def fold_text(value):
            return ''.join(c for c in unicodedata.normalize('NFD',str(value)).casefold().replace('đ','d') if not unicodedata.combining(c))
        db.create_function('fold_text',1,fold_text,deterministic=True)
        try:
            total=db.execute('SELECT COUNT(*) FROM web_orders'+where,params).fetchone()[0]
            rows=db.execute('SELECT * FROM web_orders'+where+' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',params+[limit,offset])
            return {'orders':[order_view(db,row,True) for row in rows],'total':total,'limit':limit,'offset':offset,
                    'chatbotRequests':[json.loads(row['payload']) for row in db.execute('SELECT payload FROM submissions ORDER BY created_at DESC LIMIT 100')] if include_requests else []}
        finally:db.close()

    @app.patch('/api/admin/orders/{order_id}')
    def status(order_id:str,body:Status,request:Request):
        authorize(request);db=connect(db_path)
        try:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM web_orders WHERE id=?',(order_id,)).fetchone()
            if not row:raise HTTPException(404,'order_not_found')
            previous=delivery_info(db,row)
            current=previous['status']
            if current==body.status and (body.expectedArrival is None or current not in {'confirmed','delivering'}):return {'ok':True}
            transitions={'pending_confirmation':{'confirmed','cancelled'},'confirmed':{'delivering','completed','cancelled'},
                         'delivering':{'completed','cancelled'},'completed':set(),'cancelled':set()}
            if body.status!=current and body.status not in transitions[current]:raise HTTPException(409,'invalid_transition')
            if body.status=='cancelled':
                cancel_order(db,order_id)
                db.commit()
                return {'ok':True}
            clock=delivery_now()
            if body.status=='delivering' and not in_delivery_hours(clock,dispatch=True):
                raise HTTPException(409,'delivery_closed')
            now=utc_now();payload=json.loads(row['payload'])
            estimate=previous.get('estimate')
            if body.status in {'confirmed','delivering'}:
                base=clock
                desired=payload.get('delivery',{})
                if body.status=='confirmed' and desired.get('requestedSlot')=='evening' and body.expectedArrival is None:
                    raise HTTPException(409,'legacy_delivery_slot')
                if body.status=='confirmed' and desired.get('requestedDate'):
                    hour={'morning':8,'afternoon':12}.get(desired.get('requestedSlot'),8)
                    scheduled=datetime.combine(date.fromisoformat(desired['requestedDate']),datetime.min.time(),tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')).replace(hour=hour).astimezone(timezone.utc)
                    base=max(base,scheduled)
                estimate=estimate_delivery(payload['shippingAddress'].get('location'),now=base,preparation=body.status=='confirmed')
                if body.expectedArrival:
                    arrival=body.expectedArrival.astimezone(timezone.utc)
                    estimate={**estimate,'available':True,'earliestAt':arrival.isoformat(),
                              'latestAt':min(arrival+timedelta(minutes=15),arrival.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).replace(hour=18,minute=0,second=0,microsecond=0).astimezone(timezone.utc)).isoformat(),'method':'admin_estimate',
                              'notice':'Thời gian dự kiến do cửa hàng xác nhận; có thể thay đổi theo giao thông.'}
            if body.status=='delivering' and estimate and estimate.get('available'):
                arrival_day=datetime.fromisoformat(estimate['latestAt']).astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).date()
                if arrival_day!=clock.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).date():
                    raise HTTPException(409,'delivery_exceeds_hours')
            old_estimate=previous.get('estimate') or {}
            if body.status==current and old_estimate.get('available') and estimate and estimate.get('available'):
                if all(datetime.fromisoformat(old_estimate[key])==datetime.fromisoformat(estimate[key]) for key in ('earliestAt','latestAt')):
                    return {'ok':True}
            if estimate and estimate.get('available'):
                estimate={**estimate,'displayWindow':customer_delivery_window(estimate)}
            previous_estimate=previous.get('estimate') if delivery_dates_changed(previous.get('estimate'),estimate) else None
            notice=delivery_message(order_id,body.status,estimate,previous_estimate=previous_estimate)
            dispatched=previous.get('dispatchedAt') or (now if body.status=='delivering' else None)
            delivered=now if body.status=='completed' else previous.get('deliveredAt')
            db.execute("""INSERT INTO web_delivery_updates VALUES(?,?,?,?,?)
                ON CONFLICT(order_id) DO UPDATE SET payload=excluded.payload,dispatched_at=excluded.dispatched_at,delivered_at=excluded.delivered_at,updated_at=excluded.updated_at""",
                (order_id,json.dumps({'estimate':estimate,'previousEstimate':previous_estimate,'provisional':False,'message':notice},ensure_ascii=False),dispatched,delivered,now))
            # Mốc giao lưu riêng, giữ CHECK status và khóa ngoại của DB cũ.
            stored_status='confirmed' if body.status=='delivering' else body.status
            db.execute('UPDATE web_orders SET status=?,updated_at=? WHERE id=?',(stored_status,now,order_id))
            owner=db.execute('SELECT conversation_id FROM web_order_links WHERE order_id=?',(order_id,)).fetchone()
            if owner:
                db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,'assistant',?,?)",
                           (owner['conversation_id'],notice,now))
            db.commit()
            return {'ok':True}
        finally:
            if db.in_transaction:db.rollback()
            db.close()

    # Quản trị website dùng cùng phiên đăng nhập; không thay module chatbot.
    @app.get('/api/admin/session')
    def admin_session(request:Request):
        authorize(request)
        return {'authenticated': True}

    def product_view(row):
        payload=json.loads(row['payload'])
        data={'id':row['id'],'name':row['name'],'category':payload.get('web_category',''),
              'image':payload.get('image',''),'price':row['price_vnd'],'stock':row['stock_quantity'],
              'active':bool(row['active'])}
        return {**data,'revision':fingerprint(data)}

    @app.get('/api/admin/products')
    def admin_products(request:Request):
        authorize(request)
        db=connect(db_path)
        try:
            rows=db.execute("SELECT p.*,v.price_vnd,v.stock_quantity FROM products p JOIN product_variants v ON v.id=p.id||'-std' ORDER BY p.rowid")
            return {'products':[product_view(row) for row in rows]}
        finally:db.close()

    @app.patch('/api/admin/products/{product_id}')
    def update_product(product_id:str,body:ProductUpdate,request:Request):
        authorize(request)
        db=connect(db_path)
        try:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT p.*,v.price_vnd,v.stock_quantity FROM products p JOIN product_variants v ON v.id=p.id||'-std' WHERE p.id=?",(product_id,)).fetchone()
            if not row:raise HTTPException(404,'product_not_found')
            if product_view(row)['revision']!=body.expectedRevision:
                raise HTTPException(409,'product_changed_reload')
            db.execute("UPDATE product_variants SET price_vnd=?,stock_quantity=?,stock_status=? WHERE id=?",
                       (body.price,body.stock,'in_stock' if body.stock else 'out_of_stock',product_id+'-std'))
            db.execute('UPDATE products SET active=?,updated_at=? WHERE id=?',(int(body.active),utc_now(),product_id))
            row=db.execute("SELECT p.*,v.price_vnd,v.stock_quantity FROM products p JOIN product_variants v ON v.id=p.id||'-std' WHERE p.id=?",(product_id,)).fetchone()
            result=product_view(row)
            db.commit()
            return result
        finally:
            if db.in_transaction:db.rollback()
            db.close()

    @app.get('/api/admin/overview')
    def admin_overview(request:Request):
        authorize(request)
        db=connect(db_path)
        today=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
        days=[today-timedelta(days=i) for i in range(6,-1,-1)]
        start=datetime.combine(days[0],datetime.min.time(),tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')).astimezone(timezone.utc).isoformat()
        try:
            counts={key:0 for key in ('pending_confirmation','confirmed','delivering','completed','cancelled')}
            for row in db.execute("SELECT CASE WHEN status='confirmed' AND EXISTS(SELECT 1 FROM web_delivery_updates d WHERE d.order_id=web_orders.id AND d.dispatched_at IS NOT NULL) THEN 'delivering' ELSE status END status,COUNT(*) n FROM web_orders GROUP BY 1"):
                counts[row['status']]=row['n']
            trend={str(day):0 for day in days}
            for row in db.execute("SELECT date(created_at,'+7 hours') day,COUNT(*) n FROM web_orders WHERE created_at>=? GROUP BY day",(start,)):
                if row['day'] in trend:trend[row['day']]=row['n']
            products=[product_view(row) for row in db.execute("SELECT p.*,v.price_vnd,v.stock_quantity FROM products p JOIN product_variants v ON v.id=p.id||'-std' ORDER BY v.stock_quantity,p.name")]
            return {
                'orders':counts,'totalOrders':sum(counts.values()),
                'completedMerchandiseValue':db.execute("SELECT COALESCE(SUM(subtotal),0) FROM web_orders WHERE status='completed'").fetchone()[0],
                'todayOrders':trend[str(today)],
                'trend':[{'day':day,'count':count} for day,count in trend.items()],
                'products':{'total':len(products),'active':sum(p['active'] for p in products),
                            'lowStock':[p for p in products if p['active'] and p['stock'] is not None and p['stock']<=10],
                            'unknownStock':sum(p['active'] and p['stock'] is None for p in products)},
                'consultationCount':db.execute('SELECT COUNT(*) FROM submissions').fetchone()[0],
                'ticketCount':db.execute('SELECT COUNT(*) FROM tickets').fetchone()[0],
                'recentOrders':[order_view(db,row,True) for row in db.execute('SELECT * FROM web_orders ORDER BY created_at DESC,id DESC LIMIT 5')],
                'updatedAt':utc_now()
            }
        finally:db.close()

    @app.get('/api/admin/requests')
    def admin_requests(request:Request):
        authorize(request)
        db=connect(db_path)
        try:
            records=[]
            for table,kind in (('submissions','consultation'),('tickets','ticket')):
                for row in db.execute(f'SELECT id,payload,created_at FROM {table} ORDER BY created_at DESC LIMIT 100'):
                    records.append({**json.loads(row['payload']),'id':row['id'],'created_at':row['created_at'],'recordType':kind})
            records.sort(key=lambda record:record['created_at'],reverse=True)
            return {'records':records,'limitPerType':100,
                    'total':db.execute('SELECT (SELECT COUNT(*) FROM submissions)+(SELECT COUNT(*) FROM tickets)').fetchone()[0]}
        finally:db.close()

    chatbot=create_chatbot(catalog_repository=WebsiteCatalogRepository(db_path),knowledge_repository=EmptyKnowledgeRepository(),db_path=db_path,chat_mode=chat_config.CHAT_MODE,knowledge_mode='empty',order_tools_factory=create_website_order_tools,order_updates_reader=read_order_updates)
    # Giữ nguyên chatbot: chỉ thích ứng HTML ở lớp website.
    @app.get('/chatbot/', include_in_schema=False)
    def chatbot_page():
        html=(ROOT/'chatbot/static/index.html').read_text(encoding='utf-8')
        html=html.replace('"/static/', '"/chatbot/static/')
        return HTMLResponse(html, headers={'Cache-Control':'no-store'})

    # JS chatbot hiện tại gọi /api/... tuyệt đối. Cùng các handler/session,
    # không tạo service khác hay bỏ qua kiểm tra Bearer/conversation.
    for route in chatbot.routes:
        if isinstance(route, APIRoute) and (route.path.startswith('/api/') or route.path == '/health'):
            app.router.routes.append(route)
    app.mount('/chatbot',chatbot)
    app.mount('/website',StaticFiles(directory=ROOT/'static',html=True),name='website_alias')
    @app.get('/',include_in_schema=False)
    def index():return FileResponse(ROOT/'static/index.html')
    # Cho đường dẫn tương đối hiện có hoạt động; chỉ public static/, không public DB/source.
    app.mount('/',StaticFiles(directory=ROOT/'static',html=True),name='storefront')
    return app

app=create_app()
if __name__=='__main__':
    import uvicorn
    port=int(os.getenv('PORT','8000'))
    import sys
    if '--open' in sys.argv:
        import threading, urllib.request, webbrowser
        def open_browser():
            for _ in range(60):
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as r:
                        if json.load(r).get('status')=='ok':
                            webbrowser.open(f'http://127.0.0.1:{port}');return
                except Exception:time.sleep(0.5)
        threading.Thread(target=open_browser,daemon=True).start()
    uvicorn.run(app,host='127.0.0.1',port=port)
