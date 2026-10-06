"""Hợp đồng catalog và nơi chọn nguồn; chưa có adapter tương lai."""

from typing import Protocol

from app.schemas import CatalogCapabilities, ProductResult, SearchFilters, SearchResult


class CatalogRepository(Protocol):
    """Một nguồn chỉ cần cung cấp đúng ba phương thức này."""

    def search_products(self, filters: SearchFilters) -> SearchResult: ...

    def get_product(self, product_id: str) -> ProductResult: ...

    def get_capabilities(self) -> CatalogCapabilities: ...


def create_catalog_repository(mode: str, database_path=None) -> CatalogRepository:
    """Chọn nguồn một lần tại điểm chạy, không chọn nguồn trong chatbot."""
    if mode == "empty":
        from app.repositories.empty_catalog import EmptyCatalogRepository
        return EmptyCatalogRepository()
    if mode == "mock":
        from app.repositories.mock_catalog import MockCatalogRepository
        return MockCatalogRepository()
    if mode == "local_demo":
        from app.config import DATABASE_PATH
        from app.repositories.local_catalog import LocalCatalogRepository
        return LocalCatalogRepository(database_path if database_path is not None else DATABASE_PATH)
    raise ValueError("Nguồn catalog chưa được hỗ trợ.")


def safe_search_products(
    repository: CatalogRepository, filters: SearchFilters, data_mode: str = "unknown",
) -> SearchResult:
    """Đổi exception nguồn thành trạng thái lỗi, không lộ nội dung lỗi riêng."""
    try:
        return repository.search_products(filters)
    except Exception:
        # Chỉ bắt rộng ở biên nguồn: adapter tương lai có thể có lỗi kết nối.
        return {"status": "error", "data_mode": data_mode, "products": [], "error": "source_error"}
