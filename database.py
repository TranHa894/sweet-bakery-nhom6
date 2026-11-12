"""SQLite dùng chung cho catalog, đơn website, lịch sử chatbot và sự kiện Auto-Alert & SLA."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(1, str(ROOT / 'chatbot'))
from app.storage import open_storage, utc_now
from scripts.database import seed_database
from app.config import parse_env_text
from automation_alerts import ensure_automation_schema

env_path=ROOT/'.env'
if env_path.is_file() and not env_path.is_symlink():
    for key,value in parse_env_text(env_path.read_text(encoding='utf-8-sig')).items():
        if key.startswith(('STORE_','DELIVERY_')):
            os.environ.setdefault(key,value)


DB_PATH = Path(os.environ.get('SWEET_DB_PATH', str(ROOT / 'runtime' / 'sweet_bakery.sqlite3'))).resolve()


def connect(path=DB_PATH):
    return open_storage(path)


def initialize(path=DB_PATH):
    seed = json.loads((ROOT / 'static/products.json').read_text(encoding='utf-8'))
    document = {'is_demo': True, 'source': 'local_demo', 'seed_version': 'sweet-integrated-1',
                'products': [], 'toppings': [], 'policies': [
        {'id': 'sweet-checkout', 'title': 'Đặt hàng và giao hàng', 'content': 'Đây là website học tập Sweet Bakery. Đặt hàng tại giỏ hàng và điền thông tin giao hàng. Đơn được lưu trong database local. Phí giao hàng và thời gian giao chờ xác nhận. Thanh toán khi nhận hàng (COD); chưa có thanh toán online.', 'version': '1', 'is_mock': True},
        {'id': 'sweet-ingredients', 'title': 'Thành phần và dị ứng', 'content': 'Chưa có dữ liệu thành phần, dị ứng, thời hạn và hướng dẫn bảo quản đã xác minh. Cần hỏi cửa hàng trước khi dùng; không suy đoán sản phẩm an toàn với dị ứng.', 'version': '1', 'is_mock': True}],
        'business_settings': {'id': 'store', 'version': 'sweet-1', 'is_demo': True, 'timezone': 'Asia/Ho_Chi_Minh', 'opens_at': '08:00', 'closes_at': '20:00', 'fulfillment_modes': ['delivery'], 'delivery_regions': {}}}
    for p in seed:
        document['products'].append({
            'id': p['id'], 'name': p['name'], 'aliases': [p['name'], p['id']],
            'category': {'cake': 'bánh kem', 'mini': 'bánh ngọt nhỏ', 'drink': 'đồ uống'}[p['category']],
            'description': f"{p['name']} trong danh mục Sweet Bakery của nhóm 6.",
            'flavor': None, 'occasions': [], 'active': True,
            'variants': [{'id': p['id']+'-std', 'size': 'Tiêu chuẩn', 'price_vnd': p['price'], 'servings': None, 'stock_quantity': 100, 'stock_status': 'in_stock'}],
            'allergen': None, 'allergen_info': {'status': 'unknown', 'items': [], 'note': 'Chưa xác minh thành phần.'},
            'customization': None, 'min_lead_hours': None, 'writing_supported': p['category']=='cake',
            'max_cake_text_length': 100, 'cake_text_price_vnd': 0, 'topping_ids': [],
            'storage': None, 'shelf_life_hours': None, 'source': 'local_demo', 'is_mock': True, 'is_demo': True,
            'web_category': p['category'], 'image': p['image']})
    # Seed dùng helper cũ; file trung gian không chứa dữ liệu khách.
    seed_path = Path(path).parent / 'catalog-seed.json'
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
    with connect(path) as db:
        seed_database(db, seed_path)
        db.executescript('''
          CREATE TABLE IF NOT EXISTS web_orders (
            id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
            payload_hash TEXT NOT NULL, customer_name TEXT NOT NULL,
            phone TEXT NOT NULL, email TEXT, payload TEXT NOT NULL,
            subtotal INTEGER NOT NULL CHECK(subtotal>=0), shipping_fee INTEGER,
            status TEXT NOT NULL CHECK(status IN ('pending_confirmation','confirmed','completed','cancelled')),
            payment_method TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS web_order_items (
            id INTEGER PRIMARY KEY, order_id TEXT NOT NULL REFERENCES web_orders(id),
            product_id TEXT NOT NULL REFERENCES products(id), variant_id TEXT NOT NULL REFERENCES product_variants(id),
            product_name TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 99),
            unit_price INTEGER NOT NULL CHECK(unit_price>=0)
          );
          CREATE TABLE IF NOT EXISTS web_order_links (
            order_id TEXT PRIMARY KEY REFERENCES web_orders(id),
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            draft_id TEXT NOT NULL REFERENCES drafts(id),
            revision INTEGER NOT NULL CHECK(revision>=0),
            payload TEXT NOT NULL,
            UNIQUE(draft_id,revision)
          );
          CREATE INDEX IF NOT EXISTS web_order_links_owner ON web_order_links(conversation_id,order_id);
          CREATE TABLE IF NOT EXISTS web_delivery_updates (
            order_id TEXT PRIMARY KEY REFERENCES web_orders(id),
            payload TEXT NOT NULL, dispatched_at TEXT, delivered_at TEXT, updated_at TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS web_orders_date ON web_orders(created_at);
        ''')
        ensure_automation_schema(db)
        db.commit()
    db.close()


def catalog(path=DB_PATH):
    db = connect(path)
    try:
        result=[]
        for r in db.execute('SELECT p.*, v.price_vnd, v.stock_quantity FROM products p JOIN product_variants v ON v.id=p.id||\'-std\' WHERE p.active=1 ORDER BY p.rowid'):
            p=json.loads(r['payload'])
            result.append({'id':r['id'],'name':r['name'],'price':r['price_vnd'],'stock':r['stock_quantity'], 'category':p['web_category'],'image':p['image']})
        return result
    finally:
        db.close()
