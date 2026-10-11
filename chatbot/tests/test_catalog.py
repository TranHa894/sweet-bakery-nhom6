"""Kiểm tra hợp đồng và dữ liệu, không phụ thuộc văn phong câu trả lời."""

from copy import deepcopy
import json

import pytest

from app.repositories.catalog import create_catalog_repository
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.schemas import validate_product


def test_mock_has_five_stable_labeled_products():
    result = MockCatalogRepository().search_products({})
    assert result["status"] == "success"
    assert {item["id"] for item in result["products"]} == {f"mock-{i:03}" for i in range(1, 6)}
    assert all(item["source"] == "mock" and item["is_mock"] for item in result["products"])
    for product in result["products"]:
        validate_product(product)


def test_four_repository_statuses_are_distinct(tmp_path):
    repo = MockCatalogRepository()
    statuses = {
        EmptyCatalogRepository().search_products({})["status"],
        repo.search_products({"query": "khongtontai"})["status"],
        repo.search_products({})["status"],
        MockCatalogRepository(tmp_path / "missing.json").search_products({})["status"],
    }
    assert statuses == {"unconfigured", "no_results", "success", "error"}


def test_get_product_returns_full_product_and_explicit_status(tmp_path):
    repo = MockCatalogRepository()
    found = repo.get_product("mock-001")
    assert found["status"] == "success" and len(found["product"]["variants"]) == 2
    assert repo.get_product("missing")["status"] == "no_results"
    assert EmptyCatalogRepository().get_product("mock-001")["status"] == "unconfigured"
    assert MockCatalogRepository(tmp_path / "missing.json").get_product("mock-001")["status"] == "error"


def test_unknown_values_remain_unknown():
    product = MockCatalogRepository().get_product("mock-005")["product"]
    variant = product["variants"][0]
    assert variant["price_vnd"] is None and variant["servings"] is None
    assert variant["stock_status"] == "unknown"
    assert product["allergen"] is None
    assert MockCatalogRepository().search_products({"product_ids": ["mock-005"], "max_price_vnd": 300000})["status"] == "no_results"


def test_budget_boundary_and_filtered_variants():
    repo = MockCatalogRepository()
    filters = {"product_ids": ["mock-003"], "max_price_vnd": 300000, "price_inclusive": False}
    strict = repo.search_products(filters)["products"][0]
    assert [variant["price_vnd"] for variant in strict["variants"]] == [220000]
    filters["price_inclusive"] = True
    inclusive = repo.search_products(filters)["products"][0]
    assert len(inclusive["variants"]) == 2


def test_price_and_servings_must_match_same_variant():
    result = MockCatalogRepository().search_products({
        "product_ids": ["mock-001"], "max_price_vnd": 300000, "servings": 8,
    })
    assert result["status"] == "no_results"


def test_filters_for_size_flavor_and_words():
    repo = MockCatalogRepository()
    result = repo.search_products({"flavor": "DÂU", "size": "16cm"})
    assert [item["id"] for item in result["products"]] == ["mock-002"]
    assert len(result["products"][0]["variants"]) == 1
    assert repo.search_products({"query": "tart chanh"})["products"][0]["id"] == "mock-005"


def test_callers_cannot_change_repository_data():
    repo = MockCatalogRepository()
    product = repo.get_product("mock-001")["product"]
    product["variants"][0]["price_vnd"] = 1
    assert repo.get_product("mock-001")["product"]["variants"][0]["price_vnd"] == 250000


@pytest.mark.parametrize("damage", ["not_json", "missing_field", "duplicate_id", "not_mock", "negative_price"])
def test_invalid_fixture_returns_source_error(tmp_path, damage):
    products = MockCatalogRepository().search_products({})["products"]
    document = {"data_mode": "mock", "is_mock": True, "products": deepcopy(products)}
    if damage == "missing_field":
        del document["products"][0]["flavor"]
    elif damage == "duplicate_id":
        document["products"][1]["id"] = document["products"][0]["id"]
    elif damage == "not_mock":
        document["products"][0]["is_mock"] = False
    elif damage == "negative_price":
        document["products"][0]["variants"][0]["price_vnd"] = -1
    path = tmp_path / "fixture.json"
    path.write_text("broken{" if damage == "not_json" else json.dumps(document), encoding="utf-8")
    result = MockCatalogRepository(path).search_products({})
    assert result["status"] == "error" and result["error"] == "invalid_mock_data"


def test_factory_does_not_add_future_sources():
    assert isinstance(create_catalog_repository("mock"), MockCatalogRepository)
    assert isinstance(create_catalog_repository("empty"), EmptyCatalogRepository)
    with pytest.raises(ValueError):
        create_catalog_repository("database")
