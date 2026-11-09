from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import create_app
from database import initialize,connect,catalog
import pytest

@pytest.fixture
def service(tmp_path):
    db=tmp_path/'sweet.sqlite3'
    with TestClient(create_app(db,admin_password='test-password')) as client:
        yield client,db

def payload(qty=2):
    return {'customer':{'fullName':'Khách kiểm thử','phone':'0912345678','email':None},'shippingAddress':{'province':'Hà Nội','ward':'Phường kiểm thử','addressLine':'123 Đường kiểm thử'},'delivery':{'requestedDate':None,'requestedSlot':'afternoon'},'cakeMessage':'Chúc vui','note':'Dữ liệu kiểm thử','paymentMethod':'cod','consent':True,'items':[{'productId':'SP0024','quantity':qty}]}

def send(c,p=None,key='test-order-key'):
    return c.post('/api/orders',json=p or payload(),headers={'Idempotency-Key':key})

def test_round_trip_stock_and_admin(service):
    c,db=service
    assert len(c.get('/api/products').json())==24
    assert c.get('/api/admin/orders').status_code==401
    r=send(c);assert r.status_code==201,r.text
    data=r.json();assert data['subtotal']==700000 and data['shippingFee'] is None
    assert send(c).json()['orderId']==data['orderId']
    assert send(c,payload(3)).status_code==409
    initialize(db) # restart/seed không reset stock hay đơn
    assert next(p for p in catalog(db) if p['id']=='SP0024')['stock']==98
    assert c.post('/api/admin/login',json={'password':'wrong'}).status_code==401
    assert c.post('/api/admin/login',json={'password':'test-password'}).status_code==200
    orders=c.get('/api/admin/orders').json()['orders'];assert len(orders)==1
    assert orders[0]['customer']['fullName']=='Khách kiểm thử'
    url='/api/admin/orders/'+data['orderId']
    assert c.patch(url,json={'status':'completed'}).status_code==409
    assert c.patch(url,json={'status':'confirmed'}).status_code==200
    assert c.patch(url,json={'status':'cancelled'}).status_code==200
    assert c.patch(url,json={'status':'cancelled'}).status_code==200
    assert next(p for p in catalog(db) if p['id']=='SP0024')['stock']==100
    assert c.patch(url,json={'status':'confirmed'}).status_code==409
    c.post('/api/admin/logout');assert c.get('/api/admin/orders').status_code==401

@pytest.mark.parametrize('qty',[0,-1,100,1.5,True,'2'])
def test_quantity_invalid(service,qty):
    c,db=service
    assert send(c,payload(qty)).status_code==422
    assert next(p for p in catalog(db) if p['id']=='SP0024')['stock']==100

@pytest.mark.parametrize('kind',['phone','name','date','consent','duplicate','price','missing','empty'])
def test_bad_payload(service,kind):
    c,_=service;p=payload()
    if kind=='phone':p['customer']['phone']='123'
    if kind=='name':p['customer']['fullName']='  '
    if kind=='date':p['delivery']['requestedDate']='2000-01-01'
    if kind=='consent':p['consent']=False
    if kind=='duplicate':p['items']*=2
    if kind=='price':p['items'][0]['price']=1
    if kind=='missing':del p['shippingAddress']
    if kind=='empty':p['items']=[]
    assert send(c,p).status_code==422

def test_stock_rollback_and_db_price(service):
    c,db=service
    with connect(db) as con:
        con.execute("UPDATE product_variants SET stock_quantity=1 WHERE product_id='SP0024'")
        con.execute("UPDATE product_variants SET price_vnd=123000 WHERE product_id='SP0001'")
    p=payload();p['items'].insert(0,{'productId':'SP0001','quantity':1})
    assert send(c,p).status_code==409
    assert next(p for p in catalog(db) if p['id']=='SP0001')['stock']==100
    p['items']=p['items'][:1];assert send(c,p).json()['subtotal']==123000


def test_chat_catalog_and_session(service):
    c,db=service
    assert c.get('/chatbot/').status_code==200
    assert c.get('/chatbot/static/chat.js').status_code==200
    r=c.post('/chatbot/api/conversations',json={});assert r.status_code==201
    s=r.json();body={'conversation_id':s['conversation_id'],'message':'giá Mousse Chanh leo'}
    assert c.post('/chatbot/api/chat',json=body).status_code==401
    r=c.post('/chatbot/api/chat',json=body,headers={'Authorization':'Bearer '+s['session_token']});assert r.status_code==200,r.text
    assert r.json()['products'][0]['id']=='SP0024'
    assert r.json()['products'][0]['variants'][0]['price_vnd']==350000
    with connect(db) as con:con.execute("UPDATE product_variants SET price_vnd=355000 WHERE product_id='SP0024'")
    r=c.post('/chatbot/api/chat',json=body,headers={'Authorization':'Bearer '+s['session_token']})
    assert r.json()['products'][0]['variants'][0]['price_vnd']==355000
    assert next(p for p in c.get('/api/products').json() if p['id']=='SP0024')['price']==355000

def test_static_and_cross_origin(service):
    c,_=service
    for url in ['/','/index.html','/thanh-toan.html','/admin.html','/script.js','/images/SP0024.webp']:
        assert c.get(url).status_code==200,url
    for url in ['/main.py','/runtime/sweet_bakery.sqlite3','/runtime/admin-password.txt']:
        assert c.get(url).status_code==404,url
    assert c.post('/api/admin/login',json={'password':'test-password'},headers={'Origin':'https://other.example'}).status_code==403
