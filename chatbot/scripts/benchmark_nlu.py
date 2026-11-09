"""Đo vài câu tổng hợp bằng model thật, chỉ ghi chỉ số/slot an toàn; không đụng DB khách."""
import argparse
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from app import config,llm_client
from app.conversation import new_conversation
from app.repositories.group_catalog import GroupCatalogRepository

CASES=[
 ("greeting","hello",[],None),
 ("coffee80","đề xuất cho tôi bánh nhỏ và cà phê đắng trong giá 80k nhé",
  [{"product_type":"mini"},{"product_type":"coffee","coffee_style":"strong"}],80000),
 ("coffee86","đề xuất cho tôi bánh nhỏ, cà phê đắng trong giá 86k nhé",
  [{"product_type":"mini"},{"product_type":"coffee","coffee_style":"strong"}],86000),
 ("tea70","cho tôi combo bánh nhỏ và trà ngọt trong giá 70k nhé",
  [{"product_type":"mini"},{"product_type":"tea","sweetness":"sweet"}],70000),
 ("vanilla90","gợi ý bánh nhỏ vị vani và cà phê béo mặn nhẹ trong giá 90k",
  [{"product_type":"mini","flavor":"vani"},{"product_type":"coffee","coffee_style":"creamy"}],90000),
]
def run(engine="legacy",limit=5,output=None):
    repo=GroupCatalogRepository(database_path=":memory:")
    extractor=(getattr(llm_client,"extract_turn_legacy",llm_client.extract_turn)
               if engine=="legacy" else llm_client.extract_turn)
    original=llm_client.request_json
    rows=[]
    metrics={}
    def measured(*args,**kwargs):
        result=original(*args,**kwargs)
        if args[1]=="/api/chat":
            metrics["calls"]=metrics.get("calls",0)+1
            if result["ok"]:
                for key in ("prompt_eval_count","eval_count","load_duration","prompt_eval_duration","eval_duration"):
                    metrics[key]=metrics.get(key,0)+(result["data"].get(key) or 0)
        return result
    for identifier,message,expected,budget in CASES[:limit]:
        metrics.clear();metrics["calls"]=0
        started=perf_counter()
        with patch.object(llm_client,"request_json",measured), patch.object(config,"NLU_ENGINE",engine):
            result=extractor(message,new_conversation(),config.OLLAMA_BASE_URL,config.OLLAMA_MODEL,
                             config.OLLAMA_TIMEOUT_SECONDS,repo)
        value=result.get("data")
        checks={}
        requests=value.requests if value else []
        if identifier=="greeting":
            checks["intent"]=bool(value and "greeting" in value.intents)
        else:
            checks["group"]=len(requests)==len(expected) and all(
                r.filters.product_type==f["product_type"] for r,f in zip(requests,expected))
            for field in ("coffee_style","flavor","sweetness"):
                wanted=[(index,f[field]) for index,f in enumerate(expected) if field in f]
                if wanted:
                    checks[field]=bool(value) and all(index<len(requests) and
                        getattr(requests[index].filters,field)==wanted_value for index,wanted_value in wanted)
            checks["budget"]=bool(value and value.bundle_budget and value.bundle_budget.budget_vnd==budget)
            checks["budget_direction"]=bool(value and value.bundle_budget and value.bundle_budget.price_inclusive
                                             and value.bundle_budget.min_budget_vnd is None)
            checks["quantity"]=bool(value and len(requests)==len(expected) and all(r.quantity==1 for r in requests))
        row={"id":identifier,"engine":engine,"seconds":round(perf_counter()-started,3),
             "error":result.get("error"),"metrics":dict(metrics),"fields":checks}
        rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    report={"engine":engine,"cases":rows,"field_scores":{}}
    for field in sorted({f for row in rows for f in row["fields"]}):
        marks=[row["fields"][field] for row in rows if field in row["fields"]]
        report["field_scores"][field]={"passed":sum(marks),"total":len(marks)}
    if output:
        root=Path(__file__).resolve().parents[1]
        target=(root/output).resolve()
        if not target.is_relative_to(root/"runtime") or target.suffix!=".json":
            raise ValueError("Chỉ ghi report JSON trong runtime chatbot.")
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine",choices=["legacy","hybrid"],default="hybrid")
    parser.add_argument("--limit",type=int,default=5)
    parser.add_argument("--output")
    args=parser.parse_args()
    print(json.dumps(run(args.engine,args.limit,args.output)["field_scores"],ensure_ascii=False))
if __name__=="__main__":main()
