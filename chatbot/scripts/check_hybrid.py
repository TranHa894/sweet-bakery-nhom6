"""Hồi quy NLU lai bằng dữ liệu tổng hợp và SQLite RAM, không truy cập DB khách."""
import io,json,unittest
from contextlib import redirect_stdout
from copy import deepcopy
from unittest.mock import patch
from app import config,llm_client
from app.conversation import handle_message,new_conversation
from app.repositories.group_catalog import GroupCatalogRepository
from app.repositories.empty_catalog import EmptyCatalogRepository
from app.knowledge_loader import EmptyKnowledgeRepository
from app.order_service import create_order_tools
from app.storage import open_storage,save_conversation,load_conversation
from app.understanding.deterministic import analyze
from app.understanding.context import pack_context,restore_context
from app.understanding.frames import SemanticFrame
from app.understanding.validation import build_query,validate_frame

class HybridChecks(unittest.TestCase):
    def setUp(self):
        self.db=open_storage(":memory:");self.addCleanup(self.db.close)
        self.repo=GroupCatalogRepository(database_path=":memory:")
        self.current=new_conversation();self.current["web_checkout"]=True
        self.mode=patch.object(config,"NLU_ENGINE","hybrid");self.mode.start();self.addCleanup(self.mode.stop)

    def extract(self,text,current=None):
        with patch.object(llm_client,"chat",side_effect=AssertionError("Unexpected model call")):
            return llm_client.extract_turn(text,current or self.current,config.OLLAMA_BASE_URL,
                config.OLLAMA_MODEL,60,self.repo)

    def turn(self,text):
        result=handle_message(text,self.repo,self.current,chat_mode="ollama",
            model=config.OLLAMA_MODEL,knowledge_repository=EmptyKnowledgeRepository(),
            storage_connection=self.db,order_tools=create_order_tools(self.repo,self.db,self.current["id"]))
        self.current=result["conversation"];return result

    def test_01_budget_paraphrases_and_field_scope(self):
        for money in ("80k","80000","80 nghìn","80.000đ"):
            result=self.extract("đề xuất bánh nhỏ và cà phê đắng trong giá "+money)
            self.assertIsNone(result["error"]);self.assertEqual(result["attempts"],0)
            value=result["data"]
            self.assertEqual(value.bundle_budget.budget_vnd,80000)
            self.assertIsNone(value.requests[0].filters.coffee_style)
            self.assertEqual(value.requests[1].filters.coffee_style,"strong")

    def test_02_tea_sweetness_never_moves_to_mini(self):
        value=self.extract("cho tôi combo bánh nhỏ và trà ngọt trong giá 70k nhé")["data"]
        self.assertIsNone(value.requests[0].filters.sweetness)
        self.assertEqual(value.requests[1].filters.sweetness,"sweet")
        self.assertNotIn("tra",value.requests[0].question)

    def test_03_four_components_keep_individual_filters(self):
        value=self.extract("tôi có 600k gợi ý bánh kem ít ngọt, trà ngọt vừa, cà phê đắng và bánh nhỏ vị vani")["data"]
        self.assertEqual(len(value.requests),4)
        self.assertEqual(value.requests[0].filters.sweetness,"low")
        self.assertEqual(value.requests[1].filters.sweetness,"medium")
        self.assertEqual(value.requests[2].filters.coffee_style,"strong")
        self.assertEqual(value.requests[3].filters.flavor,"vani")

    def test_04_per_item_caps_are_not_total(self):
        value=self.extract("bánh kem dưới 400k và cà phê trên 40k")["data"]
        self.assertIsNone(value.bundle_budget)
        self.assertEqual(value.requests[0].filters.budget_vnd,400000)
        self.assertFalse(value.requests[0].filters.price_inclusive)
        self.assertEqual(value.requests[1].filters.min_budget_vnd,40000)
        self.assertFalse(value.requests[1].filters.min_price_inclusive)

    def test_05_names_and_quantities_from_repository(self):
        value=self.extract("đặt 3 bánh cuộn vani và 2 cà phê muối")["data"]
        self.assertEqual(value.intents,["order_request"])
        self.assertEqual([i.quantity for i in value.order_items],[3,2])
        self.assertEqual(len(value.product_mentions),2)

    def test_06_price_question_does_not_order(self):
        value=self.extract("Bánh cuộn vani giá bao nhiêu?")["data"]
        self.assertEqual(value.intents,["price"]);self.assertEqual(value.action,"none")
        self.assertEqual(value.requests[0].product_mentions,["banh cuon vani"])

    def test_07_negated_order_is_information(self):
        value=self.extract("không đặt bánh cuộn vani, chỉ hỏi giá")["data"]
        self.assertEqual(value.action,"none");self.assertFalse(value.order_items)
        self.assertIn("price",value.intents)

    def test_08_actual_combo_service_and_persistence(self):
        result=self.turn("đề xuất bánh nhỏ và cà phê đắng trong giá 86k")
        self.assertIsNone(result["llm_error"])
        groups=result["response"]["recommendation_groups"]
        self.assertTrue(groups)
        self.assertTrue(all(g["total_vnd"]==80000 for g in groups))
        loaded=load_conversation(self.db,self.current["id"])
        self.assertEqual(loaded["order"],self.current["order"])

    def test_09_context_after_price_does_not_change_draft(self):
        self.turn("đặt 2 bánh cuộn vani")
        before=deepcopy(self.current["order"])
        result=self.turn("Bánh donut sô cô la hương dâu giá bao nhiêu?")
        self.assertIsNone(result["llm_error"])
        self.assertEqual([p["id"] for p in result["response"]["products"]],["SP0017"])
        self.assertEqual(self.current["order"],before)

    def test_10_reference_to_previous_product(self):
        self.turn("Bánh cuộn vani giá bao nhiêu?")
        result=self.turn("bánh đó giá bao nhiêu?")
        self.assertEqual([p["id"] for p in result["response"]["products"]],["SP0015"])

    def test_11_reference_order_stays_verified(self):
        self.turn("Bánh cuộn vani giá bao nhiêu?")
        value=self.extract("đặt cho tôi bánh này",self.current)["data"]
        self.assertEqual(value.order_items[0].reference,"last")
        self.assertIsNone(value.order_items[0].product_mention)

    def test_12_unknown_policy_has_no_invented_sources(self):
        result=self.turn("chính sách")
        self.assertFalse(result["response"]["policy"]["source_ids"])

    def test_13_allergy_needs_handoff(self):
        value=self.extract("gợi ý bánh cho người dị ứng hạt nghiêm trọng")["data"]
        self.assertEqual(value.action,"handoff")

    def test_14_model_timeout_never_falls_back_or_changes_draft(self):
        before=deepcopy(self.current)
        with patch.object(llm_client,"chat",return_value={"ok":False,"error":"timeout","content":None}):
            result=self.turn("mình đang phân vân chuyện này")
        self.assertEqual(result["llm_error"],"timeout")
        self.assertEqual(self.current["order"],before["order"])

    def test_15_model_schema_is_closed_and_small(self):
        reply={"mode":"other","intents":["out_of_scope"],"candidate_indexes":[],"continuation":"none"}
        with patch.object(llm_client,"chat",return_value={"ok":True,"content":json.dumps(reply),"error":None}) as call:
            value=llm_client.extract_turn("hôm nay trời đẹp ghê",self.current,
                config.OLLAMA_BASE_URL,config.OLLAMA_MODEL,60,self.repo)
        self.assertEqual(call.call_count,1)
        schema=call.call_args.args[3]
        self.assertEqual(len(schema["anyOf"]),4)
        for branch in schema["$defs"].values():
            self.assertLessEqual(len(branch["properties"]),4)
            self.assertFalse(branch["additionalProperties"])
        self.assertEqual(value["data"].intents,["out_of_scope"])

    def test_16_invalid_candidate_is_not_accepted(self):
        reply={"mode":"information","intents":["price"],"candidate_indexes":[999],"continuation":"none"}
        with patch.object(llm_client,"chat",return_value={"ok":True,"content":json.dumps(reply),"error":None}) as call:
            result=llm_client.extract_turn("món lạ này",self.current,config.OLLAMA_BASE_URL,
                config.OLLAMA_MODEL,60,self.repo)
        self.assertEqual(call.call_count,2)
        self.assertEqual(result["error"],"invalid_turn_json")

    def test_17_fuzzy_candidates_are_source_ids(self):
        from app.understanding.deterministic import fuzzy_candidates
        products=self.repo.search_products({})["products"]
        candidates=fuzzy_candidates("banh cuon vanii",products)
        self.assertTrue(candidates)
        self.assertTrue(all(c["id"] in {p["id"] for p in products} for c in candidates))

    def test_18_unknown_model_field_keeps_valid_fields(self):
        reply={"mode":"other","intents":["greeting"],"candidate_indexes":[],"continuation":"none","unknown":"untrusted"}
        with patch.object(llm_client,"chat",return_value={"ok":True,"content":json.dumps(reply),"error":None}):
            result=llm_client.extract_turn("hey bạn ơi",self.current,config.OLLAMA_BASE_URL,
                config.OLLAMA_MODEL,60,self.repo)
        self.assertIsNone(result["error"])
        self.assertIn("greeting",result["data"].intents)

    def test_19_invalid_query_does_not_drop_valid_other_query(self):
        frame=SemanticFrame(intents=["recommendation"])
        good=build_query(frame,intents=["recommendation"],product_mentions=[],
            question="cà phê đắng",filters={"product_type":"coffee","coffee_style":"strong"})
        bad=build_query(frame,intents=["recommendation"],product_mentions=[],
            question="bánh 100k đến 50k",filters={"product_type":"mini","min_budget_vnd":100000,"budget_vnd":50000})
        frame.queries=[good,bad]
        cleaned=validate_frame(frame)
        self.assertEqual(len(cleaned.queries),1);self.assertTrue(cleaned.issues)

    def test_20_context_v1_v2_roundtrip_preserves_order(self):
        old=deepcopy(self.current)
        old["pending_information_request"]=[{"intents":["price"],"product_ids":["SP0015"]}]
        packed=pack_context(old)
        self.assertNotIn("needs",packed)
        self.assertEqual(packed["memory_version"],2)
        self.assertEqual(restore_context(packed)["pending_information_request"],old["pending_information_request"])
        self.assertEqual(restore_context(packed)["order"],old["order"])
        self.assertEqual(old,self.current|{"pending_information_request":old["pending_information_request"]})

    def test_21_storage_migrates_only_payload_on_write(self):
        self.db.execute("INSERT INTO conversations VALUES(?,?,?)",(self.current["id"],json.dumps(self.current),"old"))
        self.db.commit()
        loaded=load_conversation(self.db,self.current["id"])
        self.assertEqual(loaded["order"],self.current["order"])
        with self.db:save_conversation(self.db,loaded)
        raw=json.loads(self.db.execute("SELECT payload FROM conversations").fetchone()[0])
        self.assertEqual(raw["memory_version"],2)
        self.assertNotIn("needs",raw)

    def test_22_trace_has_no_message_contact_or_json_values(self):
        from app.understanding.trace import emit
        from app.understanding.frames import SemanticFrame
        out=io.StringIO()
        with patch.object(config,"NLU_TRACE",True),redirect_stdout(out):
            emit("DEMO private@example.invalid 0912345678",SemanticFrame(),seconds=0,calls=0)
        self.assertNotIn("0912345678",out.getvalue())
        self.assertNotIn("private@",out.getvalue())
        self.assertIn("deterministic",out.getvalue())

    def test_23_empty_mode_does_not_invent_products(self):
        repo=EmptyCatalogRepository()
        result=handle_message("gợi ý bánh kem dưới 400k",repo,new_conversation(),
            model=config.OLLAMA_MODEL,chat_mode="ollama",storage_connection=self.db)
        self.assertFalse(result["response"]["products"])

    def test_24_two_conversations_do_not_share_memory(self):
        self.turn("Bánh cuộn vani giá bao nhiêu?")
        other=new_conversation()
        self.assertFalse(other["discussion_context"]["focus_product_ids"])
        self.assertFalse(other["order"]["slots"]["product_id"])


    def test_25_guided_selection_preserves_sweetness_and_flavor(self):
        first=self.turn("gợi ý bánh kem")
        self.assertTrue(first["response"]["quick_replies"])
        second=self.turn("Ngọt vừa")
        self.assertTrue(second["response"]["quick_replies"])
        final=self.turn("Kem/vani/trang trí")
        self.assertIsNone(final["llm_error"])
        self.assertTrue(final["response"]["products"])
        self.assertTrue(all(p["id"] in {"SP0005","SP0007","SP0008","SP0009"}
                            for p in final["response"]["products"]))

    def test_26_new_search_drops_old_budget_and_flavor(self):
        self.turn("tìm bánh kem trên 400k")
        result=self.turn("gợi ý một số loại trà")
        self.assertTrue(result["response"]["products"])
        self.assertTrue(all(p["id"] in {"SP0019","SP0020","SP0021"} for p in result["response"]["products"]))
        self.assertIsNone(result["llm_error"])

    def test_27_price_then_separate_order_only_changes_requested_item(self):
        value=self.extract("giá bánh cuộn vani bao nhiêu và đặt 2 cà phê muối")["data"]
        self.assertEqual(len(value.requests),1)
        self.assertEqual(value.requests[0].product_mentions,["banh cuon vani"])
        self.assertEqual([i.product_mention for i in value.order_items],["ca phe muoi"])
        self.assertEqual(value.order_items[0].quantity,2)

    def test_28_choose_both_uses_options_not_generic_search(self):
        value=self.extract("cả hai bánh nhé")["data"]
        self.assertEqual(value.requests[0].reference,"both")
        self.assertFalse(value.requests[0].product_mentions)
        self.assertNotIn("recommendation",value.intents)

    def test_29_model_cannot_invent_order_from_an_unclear_message(self):
        reply={"mode":"order","candidate_indexes":[0],"operation":"add_product"}
        with patch.object(llm_client,"chat",return_value={"ok":True,"content":json.dumps(reply),"error":None}):
            value=llm_client.extract_turn("cuon vanii",self.current,
                config.OLLAMA_BASE_URL,config.OLLAMA_MODEL,60,self.repo)
        self.assertEqual(value["data"].action,"none")
        self.assertFalse(value["data"].order_items)
        self.assertTrue(value["clarification"])

    def test_30_cheaper_and_lowest_keep_different_meanings(self):
        value=self.extract("còn bánh nào rẻ hơn không")["data"]
        self.assertEqual(value.requests[0].price_preference,"cheaper_than")
        self.assertEqual(value.requests[0].search_scope,"refine")
        value=self.extract("bánh nhỏ vị vani rẻ nhất")["data"]
        self.assertEqual(value.requests[0].price_preference,"lowest")

    def test_31_clear_budget_is_explicit_delta(self):
        value=self.extract("bỏ giới hạn ngân sách")["data"]
        self.assertIn("budget_vnd",value.clear_slots)
        self.assertEqual(value.action,"none")

    def test_32_quantity_update_invalidates_review_via_existing_fsm(self):
        self.turn("đặt 2 bánh cuộn vani")
        old=self.current["order"]["revision"]
        result=self.turn("đổi số lượng lên 3")
        self.assertIsNone(result["llm_error"])
        self.assertEqual(self.current["order"]["slots"]["quantity"],3)
        self.assertGreater(self.current["order"]["revision"],old)
        self.assertIsNone(self.current["order"].get("review"))

    def test_33_missing_money_unit_requests_only_that_detail(self):
        value=self.extract("gợi ý bánh nhỏ dưới 80")
        self.assertTrue(value["clarification"])
        self.assertEqual(value["field_issues"][0]["code"],"missing_unit")
        self.assertFalse(value["data"].requests)

    def test_34_model_failure_does_not_poison_next_turn(self):
        self.turn("đặt 2 bánh cuộn vani")
        before=deepcopy(self.current["order"])
        with patch.object(llm_client,"chat",return_value={"ok":False,"content":None,"error":"timeout"}):
            self.turn("mình đang phân vân chuyện này")
        result=self.turn("gợi ý bánh nhỏ và cà phê đắng trong giá 80k")
        self.assertIsNone(result["llm_error"])
        self.assertTrue(result["response"]["recommendation_groups"])
        self.assertEqual(self.current["order"],before)

    def test_35_partial_invalid_filter_retains_other_question(self):
        value=self.extract("bánh nhỏ không thích vị dâu và cà phê đắng trong giá 90k")
        self.assertTrue(value["clarification"])
        self.assertEqual(len(value["data"].requests),1)
        self.assertEqual(value["data"].requests[0].filters.product_type,"coffee")

    def test_36_invalid_quantity_never_updates_order(self):
        self.turn("đặt 2 bánh cuộn vani")
        before=deepcopy(self.current["order"])
        result=self.turn("đặt 0 bánh cuộn vani")
        self.assertTrue(result["response"]["requires_clarification"])
        self.assertEqual(self.current["order"],before)


    def test_37_policy_cancel_question_never_cancels_draft(self):
        self.turn("đặt 2 bánh cuộn vani")
        before=deepcopy(self.current["order"])
        result=self.turn("chính sách hủy đơn thế nào?")
        self.assertEqual(self.current["order"],before)
        self.assertIsNotNone(result["response"]["policy"])

    def test_38_any_and_more_are_explicit_advice_actions(self):
        value=self.extract("gì cũng được")["data"]
        self.assertEqual(value.requests[0].advice,"any")
        value=self.extract("xem thêm lựa chọn khác")["data"]
        self.assertEqual(value.requests[0].advice,"more")
        self.assertFalse(value.requests[0].filters.model_dump(exclude_none=True))


    def test_39_payload_packing_is_idempotent_and_future_versions_fail(self):
        packed=pack_context(self.current)
        self.assertEqual(pack_context(packed),packed)
        self.assertNotIn("memory",restore_context(packed))
        with self.assertRaises(ValueError):
            restore_context({**packed,"memory_version":3})


    def test_40_model_information_keeps_supported_storage_intent(self):
        reply={"mode":"information","intents":["storage"],"candidate_indexes":[0],"continuation":"none"}
        with patch.object(llm_client,"chat",return_value={"ok":True,"content":json.dumps(reply),"error":None}):
            value=llm_client.extract_turn("cuon vanii giữ tươi được mấy ngày",self.current,
                config.OLLAMA_BASE_URL,config.OLLAMA_MODEL,60,self.repo)
        self.assertEqual(value["data"].requests[0].intents,["storage"])

    def test_41_model_selection_uses_same_deadline_as_inference(self):
        from app.understanding.model import resolve
        with patch("app.understanding.model.monotonic",side_effect=[0,2]), \
             patch.object(llm_client,"select_model",return_value={"model":config.OLLAMA_MODEL,"error":None}) as select, \
             patch.object(llm_client,"chat",side_effect=AssertionError("Deadline passed")):
            _,error,calls=resolve("unknown",self.current,{"candidates":[]},
                config.OLLAMA_BASE_URL,"",1)
        self.assertEqual(error,"timeout");self.assertEqual(calls,0)
        self.assertEqual(select.call_args.kwargs["timeout"],1)


    def test_42_repository_failure_is_not_a_model_failure(self):
        before=deepcopy(self.current["order"])
        with patch("app.understanding.deterministic.safe_search_products",
                   return_value={"status":"error","products":[]}):
            result=self.turn("giá bánh cuộn vani")
        self.assertEqual(result["engine"],"source_error")
        self.assertIsNone(result["llm_error"])
        self.assertEqual(result["response"]["catalog_status"],"error")
        self.assertEqual(self.current["order"],before)


    def test_43_approximate_shared_budget_is_not_lost_before_groups(self):
        for prefix in ("ngân sách khoảng 80k", "tôi chỉ còn khoảng 80k", "với ngân sách 80 nghìn"):
            value=self.extract(prefix+" gợi ý bánh nhỏ và cà phê đắng")["data"]
            self.assertIsNotNone(value.bundle_budget,prefix)
            self.assertEqual(value.bundle_budget.budget_vnd,80000)
            self.assertIsNone(value.requests[0].filters.budget_vnd)
        value=self.extract("ngân sách 70k đến 90k gợi ý bánh nhỏ và cà phê")["data"]
        self.assertEqual(value.bundle_budget.min_budget_vnd,70000)
        self.assertEqual(value.bundle_budget.budget_vnd,90000)

if __name__=="__main__":unittest.main(verbosity=2)
