from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import create_app, chat_config
from app import llm_client
from app.schemas import LLMTurn
from database import connect


def test_mounted_chatbot_checkout_and_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_config, 'CHAT_MODE', 'ollama')
    db=tmp_path/'web.sqlite3'
    with TestClient(create_app(db, admin_password='test-password')) as c:
        html=c.get('/chatbot/').text
        assert '/chatbot/static/chat.js' in html
        for url in ['/chatbot/static/chat.js','/chatbot/static/style.css','/website/images/SP0014.webp']:
            assert c.get(url).status_code==200,url
        session=c.post('/chatbot/api/conversations',json={}).json()
        headers={'Authorization':'Bearer '+session['session_token']}
        value=LLMTurn.model_validate({'intents':['order_request'],'action':'start_order','order_operation':'select_product','product_mentions':['Bánh cuộn trà xanh'],'reference':'none','updates':{},'clear_slots':[],'ambiguous':False,'handoff_reason':'none','requests':[],'order_product_mentions':['Bánh cuộn trà xanh'],'order_items':[{'product_mention':'Bánh cuộn trà xanh','quantity':2}]})
        with patch.object(llm_client,'select_model',return_value={'model':'qwen3.5:4b','error':None}), patch.object(llm_client,'extract_turn',return_value={'data':value,'error':None,'attempts':1}):
            r=c.post('/chatbot/api/chat',headers=headers,json={'conversation_id':session['conversation_id'],'message':'đặt 2 Bánh cuộn trà xanh'})
        assert r.status_code==200,r.text
        view=r.json()['checkout'];assert view and view['stage']=='form',r.text
        form={'fullName':'Khách kiểm thử','phone':'0912345678','email':'','province':'Hà Nội','ward':'Phường thử','addressLine':'123 Đường thử','deliveryDate':'','deliverySlot':'afternoon','cakeMessage':'Chúc vui','note':'','consent':True,'items':[{'product_id':'SP0014','quantity':2}]}
        body={'conversation_id':session['conversation_id'],'draft_id':view['draft_id'],'revision':view['revision'],'action':'review','form':form}
        r=c.post('/chatbot/api/checkout',headers=headers,json=body)
        assert r.status_code==200,r.text
        view=r.json()['checkout']
        body={'conversation_id':session['conversation_id'],'draft_id':view['draft_id'],'revision':view['revision'],'action':'confirm','confirmation_token':view['confirmation_token']}
        r=c.post('/chatbot/api/checkout',headers=headers,json=body)
        assert r.status_code==200,r.text
        assert r.json()['order_id']
        assert c.post('/chatbot/api/checkout',headers=headers,json=body).json()['order_id']==r.json()['order_id']
        assert c.get('/api/admin/orders').status_code==401
        c.post('/api/admin/login',json={'password':'test-password'})
        data=c.get('/api/admin/orders').json()
        assert data['chatbotRequests']==[]
        assert len(data['orders'])==1
        assert data['orders'][0]['customer']['fullName']=='Khách kiểm thử'
        assert data['orders'][0]['orderSource']=='chatbot'
        assert data['orders'][0]['subtotal']==70000
        assert c.get('/chatbot/api/catalog',headers=headers).headers['cache-control']=='no-store'


def test_chatbot_uses_live_stock(tmp_path):
    from website_catalog import WebsiteCatalogRepository
    from database import initialize
    db=tmp_path/'stock.sqlite3';initialize(db)
    repo=WebsiteCatalogRepository(db)
    with connect(db) as con:con.execute("UPDATE product_variants SET stock_quantity=0 WHERE product_id='SP0014'")
    p=repo.get_product('SP0014')['product']
    assert p['variants'][0]['stock_status']=='out_of_stock'
    with connect(db) as con:con.execute("UPDATE products SET active=0 WHERE id='SP0014'")
    assert repo.get_product('SP0014')['status']=='no_results'
