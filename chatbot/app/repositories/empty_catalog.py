"""Nguồn chưa được cấu hình: không đồng nghĩa cửa hàng hết hàng."""

from app.schemas import CatalogCapabilities, ProductResult, SearchFilters, SearchResult


class EmptyCatalogRepository:
    def search_products(self, filters: SearchFilters) -> SearchResult:
        return {"status": "unconfigured", "data_mode": "empty", "products": [], "error": None}

    def get_product(self, product_id: str) -> ProductResult:
        return {"status": "unconfigured", "data_mode": "empty", "product": None, "error": None}

    def get_capabilities(self) -> CatalogCapabilities:
        return {
            "data_mode": "empty", "is_mock": False, "configured": False,
            "policy_available": False, "can_accept_real_orders": False,
        }
