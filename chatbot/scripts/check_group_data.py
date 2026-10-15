"""Kiểm tra kết nối menu nhóm, chỉ đọc; không gọi model hoặc tạo database."""

from collections import Counter
import json

from app.config import GROUP_CATALOG_PATH, GROUP_PROJECT_ROOT
from app.repositories.group_catalog import GroupCatalogRepository


def main() -> None:
    repository = GroupCatalogRepository()
    result = repository.search_products({})
    products = result["products"]
    report = {
        "catalog_source": "group_files", "catalog_path": str(GROUP_CATALOG_PATH),
        "status": result["status"], "error": result["error"], "data_mode": result["data_mode"],
        "product_count": len(products),
        "categories": dict(Counter(product["category"] for product in products)),
        "can_accept_real_orders": False, "can_create_demo_orders": False,
        "knowledge_mode": "empty",
        "group_orders_db_exists": (GROUP_PROJECT_ROOT / "orders.db").is_file(),
        "samples": [{"id": product["id"], "name": product["name"],
                     "price_vnd": product["variants"][0]["price_vnd"],
                     "size": product["variants"][0]["size"],
                     "stock_status": product["variants"][0]["stock_status"]}
                    for product in products[:5]],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if result["status"] not in {"success", "no_results"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
