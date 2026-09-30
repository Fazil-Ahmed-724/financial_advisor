import os
IMPORT_MAX_BYTES=int(os.getenv("MARKETPLACE_IMPORT_MAX_BYTES","10485760"))
IMPORT_MAX_ROWS=int(os.getenv("MARKETPLACE_IMPORT_MAX_ROWS","10000"))
BATCH_RANK_MAX=int(os.getenv("MARKETPLACE_BATCH_RANK_MAX","100"))
FRESHNESS={"marketplace_price":{"fresh":7,"aging":14},"demand":{"fresh":14,"aging":28},"sourcing":{"fresh":14,"aging":28},"competition":{"fresh":7,"aging":14}}
SUPPORTED_FILTERS={"marketplace","category","minimum_net_margin","minimum_roi","maximum_inventory_capital","minimum_research_score","minimum_evidence_confidence","sourcing_available","source_age_days","price_min","price_max","demand_data_available"}
SUPPORTED_SORTS={"research_score","margin","roi","demand"}
