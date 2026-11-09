"""Khung ngữ nghĩa duy nhất của tầng NLU; adapter giữ hợp đồng controller cũ."""
from pydantic import BaseModel,ConfigDict,Field
from app.schemas import InformationRequest,BundleBudget,LLMTurn,OrderItemSelection,Intent,TurnUpdates,Reference

class FieldIssue(BaseModel):
    model_config=ConfigDict(extra="forbid")
    field:str
    code:str
    question:str
    target:int|None=None

class SemanticFrame(BaseModel):
    model_config=ConfigDict(extra="forbid")
    intents:list[Intent]=Field(default_factory=list)
    queries:list[InformationRequest]=Field(default_factory=list,max_length=4)
    budget:BundleBudget|None=None
    operation:str="none"
    action:str="none"
    mentions:list[str]=Field(default_factory=list)
    order_mentions:list[str]=Field(default_factory=list)
    items:list[OrderItemSelection]=Field(default_factory=list)
    reference:Reference="none"
    order_reference:Reference|None=None
    continuation:str="none"
    updates:dict=Field(default_factory=dict)
    clear:list[str]=Field(default_factory=list)
    ambiguous:bool=False
    order_ambiguous:bool=False
    negated:bool=False
    handoff_reason:str="none"
    issues:list[FieldIssue]=Field(default_factory=list)
    provenance:dict=Field(default_factory=dict)
    needs_model:bool=False

    def as_turn(self):
        intents=list(dict.fromkeys(self.intents or ["fallback"]))
        return LLMTurn(intents=intents,action=self.action,order_operation=self.operation,
            product_mentions=self.mentions,order_product_mentions=self.order_mentions,
            order_items=self.items,reference=self.reference,order_reference=self.order_reference,
            continuation=self.continuation,updates=TurnUpdates.model_validate(self.updates),
            clear_slots=self.clear,ambiguous=self.ambiguous,order_ambiguous=self.order_ambiguous,
            order_negated=self.negated,order_update=self.operation=="update_slots",
            handoff_reason=self.handoff_reason,requests=self.queries,bundle_budget=self.budget)
