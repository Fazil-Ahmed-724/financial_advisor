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
