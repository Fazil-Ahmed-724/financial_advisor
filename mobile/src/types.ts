export type AccountType =
  | 'cash'
  | 'investment'
  | 'income'
  | 'expense'
  | 'liability'
  | 'equity';

export type Account = {
  id: string;
  name: string;
  type: AccountType;
  currency: 'PKR';
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type AccountBalance = { account: Account; balance: string };
export type Dashboard = {
  currency: 'PKR';
  cash_balance: string;
  investment_book_value: string;
  liability_balance: string;
  net_worth_book_value: string;
  confirmed_property_value: string;
  net_worth_with_confirmed_property: string;
  property_value_basis: 'user_confirmed_only';
  confirmed_resale_inventory_value: string;
  net_worth_with_confirmed_assets: string;
  inventory_value_basis: 'user_confirmed_only';
  monthly_essential_expenses: string;
  reserve_months: number;
  reserve_target: string;
  protected_emergency_cash: string;
  investable_cash: string;
  valuation_basis: 'ledger_book_value';
  market_values_available: false;
};

export type FinancialProfile = {
  monthly_essential_expenses: string;
  reserve_months: number;
  currency: 'PKR';
  created_at: string;
  updated_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
};

export type InvestmentTrade = {
  id: string; side: 'BUY' | 'SELL'; symbol: string; trade_date: string;
  quantity: string; execution_price: string; fees: string; gross_amount: string;
  net_proceeds: string | null; fifo_cost_basis: string | null;
  realized_gain_loss: string | null; investment_account_id: string;
  cash_account_id: string; external_reference: string | null;
  execution_boundary: 'recorded_external_transaction';
};

export type InvestmentLot = {
  id: string; buy_trade_id: string; investment_account_id: string; symbol: string;
  acquired_on: string; original_quantity: string; remaining_quantity: string;
  original_cost: string; remaining_cost: string;
};

export type Holding = {
  symbol: string; investment_account_id: string; quantity: string;
  remaining_book_cost: string; realized_gain_loss: string; currency: 'PKR';
  valuation_basis: 'ledger_book_value'; lots: InvestmentLot[];
};

export type SaleAnalysis = {
  id: string; symbol: string; quantity: string; hypothetical_price: string;
  estimated_fees: string; gross_proceeds: string; fifo_cost_basis: string;
  gross_profit_loss: string; estimated_tax: string | null; net_proceeds: string;
  net_profit_loss: string; tax_status: string; assumptions: Record<string, unknown>;
  excluded_items: string[]; calculated_at: string; result_type: 'estimate_only';
  order_placed: false;
};

export type Decision = {
  id: string; trade_id: string | null; sale_analysis_id: string | null;
  decision_date: string; instrument: string; action_considered: 'BUY' | 'SELL' | 'HOLD' | 'AVOID';
  rationale: string; goal: string; expected_holding_period: string; risk_factors: string;
  expected_outcome: string; confidence: string | null; planned_review_date: string | null;
  exit_conditions: string | null; created_at: string;
};

export type DecisionReview = {
  id: string; what_happened: string; assumptions_held: string; assumptions_failed: string;
  lessons_learned: string; outcome_snapshot: Record<string, unknown>;
  process_snapshot: { positive_count: number; answered_count: number; explanation: string;
    financial_outcome_used_in_score: false }; created_at: string;
};

export type DecisionDetail = Decision & {
  outcome: Record<string, unknown>; reviews: DecisionReview[];
  process_and_outcome_are_separate: true; informational_only: true; order_placed: false;
};
export type Book = { id:string; title:string; author:string; edition:string|null; publication_year:number|null; topic:string; source:string; language:string; original_filename:string; media_type:string; file_size:number; checksum_sha256:string; extraction_version:number; ingestion_status:string; status_detail:string|null; created_at:string; updated_at:string };
export type BookPassage = { id:string; book_id:string; book_title:string; author:string; reference_type:string; reference_label:string; excerpt:string; extraction_version:number; learning_support:true; market_data:false; buy_sell_instruction:false };
export type PropertyListing = { id:string; city:'Karachi'; source_type:'user_entered'|'authorized_export'; source_name:string; canonical_url:string|null; source_id:string|null; observed_at:string; listing_status:string|null; purpose:'sale'|'rent'; property_type:string; area_name:string; area_amount:string; area_unit:string; asking_amount:string; attributes:Record<string,unknown>; information_quality:string; asking_price_status:'unverified_asking_price'; confirmed_transaction_price:false; stale:boolean; stale_after_days:number; owned_by_user:boolean; confirmed_valuation:string|null; valuation_confirmed_at:string|null; created_at:string };
export type OpportunityAnalysis = { id:string; domain:string; analysis_type:string; source_evidence:Record<string,unknown>; assumptions:Record<string,unknown>; calculated_metrics:Record<string,unknown>; recommendation:null; limitations:string[]; analyzer_version:string; calculated_at:string; estimate_only:true; transaction_executed:false };
export type MarketplaceListing = { id:string; source_method:'user_entered'|'authorized_export'|'permitted_api'; source_platform:'Daraz'|'Temu'|'SHEIN'|'Other'; product_name:string; sku:string|null; source_listing_id:string|null; canonical_url:string|null; observed_at:string; currency:string; source_price:string; attributes:Record<string,unknown>; evidence:Record<string,unknown>; expected_karachi_selling_price:string|null; local_sales_channel:string|null; information_quality:string; stale:boolean; stale_after_days:number; source_data_status:'user_or_authorized_unverified'; purchase_executed:false; marketplace_listing_created:false; confirmed_inventory_value:string|null; inventory_valued_at:string|null; created_at:string };
export type MarketplaceOutcome = { id:string; analysis_id:string; recorded_at:string; purchased_quantity:string; actual_purchase_cost:string; actual_other_costs:string; sold_quantity:string; actual_sales_revenue:string; actual_sales_fees:string; returned_quantity:string; return_costs:string; remaining_quantity:string; notes:string|null; actual_net_result:string; forecast_error:string|null; assumption_differences:Record<string,unknown>; created_at:string; external_transactions_only:true; success_label:'not_assigned' };
export type IntelligenceProduct = { id:string; normalized_name:string; brand:string|null; model:string|null; category:string|null; canonical_attributes:Record<string,unknown>; match_status:string; match_candidates:string[]; created_at:string; updated_at:string };
export type ResearchRanking = { id:string; product_id:string; demand_score:string|null; margin_score:string|null; competition_score:string|null; sourcing_score:string|null; logistics_score:string|null; evidence_confidence_score:string; overall_research_score:string|null; ranking_version:string; explanation:{components:Record<string,{score:string|null;reason:string}>;missing_inputs:string[];limitations:string[]};calculated_at:string;label:'Research Score' };
export type IntelligenceListItem = { product:IntelligenceProduct; latest_observation:Record<string,unknown>|null; sourcing_available:boolean; latest_ranking:ResearchRanking|null; margin:Record<string,unknown> };
export type MarketplaceImportBatch = { id:string; import_type:string; source_classification:string; original_filename:string; status:string; total_rows:number; valid_rows:number; invalid_rows:number; warning_rows:number; committed_rows:number };
export type MarketplaceImportRow = { id:string; row_number:number; raw_data:Record<string,unknown>; normalized_data:Record<string,unknown>; validation_status:'valid'|'invalid'; warnings:string[]; errors:string[]; duplicate_status:string; proposed_product_id:string|null; action:'create_product'|'attach_to_existing_product'|'skip'|'requires_review' };
export type MarketplaceImportPreview = { batch:MarketplaceImportBatch; rows:MarketplaceImportRow[] };
export type MarketplaceHistoryEvent = { type:string; at:string; data:Record<string,unknown> };
export type AssistantCitation = { source_type:string; record_id:string; date:string|null; excerpt:string; record_path:string; freshness:'fresh'|'aging'|'stale'|'undated'|'estimated'|'unverified'|'user_entered' };
export type AssistantAnswer = { answer:string; citations:AssistantCitation[]; evidence_references:Record<string,unknown>[]; freshness:string[]; limitations:string[]; mode:'deterministic'|'llm' };
export type AssistantMessage = { id:string; role:'user'|'assistant'; content:string; created_at:string; response:AssistantAnswer|null };
export type AssistantConversation = { id:string; title:string; created_at:string; updated_at:string; messages:AssistantMessage[] };
export type AssistantFeedbackCategory = 'helpful'|'inaccurate'|'unsupported'|'stale'|'confusing'|'missing_evidence';
export type AssistantFeedback = { id:string; message_id:string; category:AssistantFeedbackCategory; comment:string|null; status:'submitted'|'reviewed'|'dismissed'; review_note:string|null; fixture_selected:boolean; response_mode:'deterministic'|'llm'|'unknown'; citation_ids:string[]; source_dates:string[]; freshness:string[]; evaluation_metadata:Record<string,unknown>; created_at:string; updated_at:string; financial_action:false };
export type FeedbackFixtureExport = { format_version:'assistant-feedback-regression-v1'; sanitized:true; confirmed:true; automatic_training:false; automatic_prompt_or_provider_change:false; requires_manual_test_implementation:true; cases:Record<string,unknown>[] };
