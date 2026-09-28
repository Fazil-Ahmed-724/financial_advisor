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
export type TokenResponse = {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
};
