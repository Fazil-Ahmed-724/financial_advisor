from dataclasses import dataclass
from typing import Any, Protocol
from fastapi import HTTPException

@dataclass(frozen=True)
class AnalysisContext:
    session: Any
    user_id: Any

class OpportunityAnalyzer(Protocol):
    domain: str
    analysis_type: str
    version: str
    def analyze(self, context: AnalysisContext, payload: Any) -> dict: ...

class DataSourceAdapter(Protocol):
    domain: str
    name: str
    def normalize(self, payload: Any) -> dict: ...

class OpportunityRegistry:
    def __init__(self): self._analyzers={};self._adapters={}
    def register_analyzer(self, analyzer): self._analyzers[(analyzer.domain,analyzer.analysis_type)]=analyzer
    def register_adapter(self, adapter): self._adapters[(adapter.domain,adapter.name)]=adapter
    def analyzer(self,domain,analysis_type):
        found=self._analyzers.get((domain,analysis_type))
        if not found: raise HTTPException(404,f"Unknown opportunity analyzer: {domain}/{analysis_type}")
        return found
    def adapter(self,domain,name):
        found=self._adapters.get((domain,name))
        if not found: raise HTTPException(404,f"Unknown data-source adapter: {domain}/{name}")
        return found
    def domains(self): return sorted({domain for domain,_ in self._analyzers})

registry=OpportunityRegistry()
