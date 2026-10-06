"""Ví dụ tiếng Việt, nhiều intent và liên kết thực thể mơ hồ."""

import json

import pytest

from app.nlu import analyze_message
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.repositories.mock_catalog import MockCatalogRepository
from app.text_utils import normalize_text, phrase_spans


def test_original_and_normalized_text_are_separate():
    message = "  Giá và SIZE bánh SÔ-CÔ-LA?  "
    result = analyze_message(message, MockCatalogRepository())
    assert result["raw_text"] == message
    assert result["normalized_text"] == "gia va size banh so co la"
    assert {"price", "size"} <= set(result["intents"])
    assert result["product_ids"] == ["mock-001"]


@pytest.mark.parametrize(("message", "intent"), [
    ("Xin chào", "greeting"), ("giá bánh socola", "price"),
    ("size bánh dâu", "size"), ("hương vị bánh vani", "flavor"),
    ("bánh trà xanh còn hàng không", "availability"),
    ("gợi ý bánh cho 6 người", "recommendation"),
    ("chính sách giao hàng", "policy"), ("đặt 2 bánh socola", "order_request"),
    ("abcdef", "fallback"),
])
def test_intents(message, intent):
    assert intent in analyze_message(message, MockCatalogRepository())["intents"]


@pytest.mark.parametrize(("message", "expected"), [
    ("socola dưới 300k", [300000]), ("ngân sách 1,5 triệu", [1500000]),
    ("tối đa 300.000 đồng", [300000]), ("ngân sách 250000", [250000]),
    ("cho 6 người, mua 2 bánh", []),
])
def test_money_is_separate_from_people_and_quantity(message, expected):
    result = analyze_message(message, EmptyCatalogRepository())
    assert result["budgets_vnd"] == expected


def test_entities_in_empty_mode_do_not_require_products():
    result = analyze_message("muốn vị xoài dưới 300k cho 6 người, 2 bánh", EmptyCatalogRepository())
    assert result["flavors"] == ["xoai"]
    assert result["servings"] == 6 and result["quantity"] == 2
    assert result["product_ids"] == [] and result["catalog_status"] == "unconfigured"


@pytest.mark.parametrize("message", [
    "socola 300k và dâu 200k", "bánh socola cho 6 người và bánh dâu cho 10 người",
    "socola hay dâu cho 8 người", "ngân sách 200k hay 300k",
    "mua 0 bánh", "cho 0 người", "không thích socola",
])
def test_ambiguous_or_unsupported_conditions_need_clarification(message):
    assert analyze_message(message, MockCatalogRepository())["requires_clarification"]


def test_shared_question_without_attribute_values_can_compare_two_products():
    result = analyze_message("giá và size bánh socola và bánh dâu", MockCatalogRepository())
    assert set(result["product_ids"]) == {"mock-001", "mock-002"}
    assert not result["requires_clarification"]


def test_names_aliases_and_new_flavor_come_from_repository(tmp_path):
    products = MockCatalogRepository().search_products({})["products"]
    product = products[0]
    product.update(id="new-id", name="Bánh kem xoài", aliases=["mango thử nghiệm"], flavor="xoài")
    path = tmp_path / "new_mock.json"
    path.write_text(json.dumps({"data_mode": "mock", "is_mock": True, "products": [product]}, ensure_ascii=False), encoding="utf-8")
    repo = MockCatalogRepository(path)
    result = analyze_message("giá và size mango thử nghiệm", repo)
    assert result["product_ids"] == ["new-id"]
    assert analyze_message("vị xoài", repo)["flavors"] == ["xoài"]
    assert analyze_message("socola", repo)["product_ids"] == []


def test_alias_collision_asks_instead_of_picking_one(tmp_path):
    products = MockCatalogRepository().search_products({})["products"][:2]
    for product in products:
        product["aliases"].append("bánh chung")
    path = tmp_path / "collision.json"
    path.write_text(json.dumps({"data_mode": "mock", "is_mock": True, "products": products}), encoding="utf-8")
    assert analyze_message("giá bánh chung", MockCatalogRepository(path))["requires_clarification"]


def test_recognized_alias_uses_source_flavor_instead_of_generic_vocabulary(tmp_path):
    product = MockCatalogRepository().get_product("mock-001")["product"]
    product["flavor"] = "chocolate"
    path = tmp_path / "different_flavor_label.json"
    path.write_text(json.dumps({"data_mode": "mock", "is_mock": True, "products": [product]}), encoding="utf-8")
    result = analyze_message("giá chocolate", MockCatalogRepository(path))
    assert result["flavors"] == ["chocolate"] and not result["requires_clarification"]


def test_phrase_matching_avoids_substrings():
    assert not phrase_spans(normalize_text("shipping"), "hi")
