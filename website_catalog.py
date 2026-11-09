"""Giữ tính năng menu chatbot mới, lấy giá/tồn kho từ database website."""
import sqlite3
from database import catalog
from app.repositories.group_catalog import GroupCatalogRepository
from app.schemas import validate_product

class WebsiteCatalogRepository(GroupCatalogRepository):
    def __init__(self, db_path):
        super().__init__(database_path=db_path)
        self.web_db_path = db_path

    def _read(self):
        result = super()._read()
        if result['status'] not in {'success', 'no_results'}:
            return result
        try:
            current = {p['id']: p for p in catalog(self.web_db_path)}
            products = []
            for product in result['products']:
                live = current.get(product['id'])
                if live is None:
                    continue
                product['name'] = live['name']
                for variant in product['variants']:
                    variant['price_vnd'] = live['price']
                    variant['stock_status'] = 'in_stock' if (live['stock'] or 0) > 0 else 'out_of_stock'
                validate_product(product)
                products.append(product)
            return {**result, 'products': products, 'status': 'success' if products else 'no_results'}
        except (sqlite3.Error, ValueError, KeyError, TypeError):
            return {**result, 'products': [], 'status': 'error', 'error': 'website_catalog_unavailable'}
