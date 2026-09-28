import { useFocusEffect } from 'expo-router'; import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { ApiError, apiRequest, newIdempotencyKey } from '@/api'; import { useAuth } from '@/auth';
import { ActionButton, Choice, Field, Screen, ui } from '@/components';
import { Account, Holding, SaleAnalysis } from '@/types';

export default function AnalysisScreen() {
  const { token } = useAuth(); const [accounts, setAccounts] = useState<Account[]>([]);
  const [holdings, setHoldings] = useState<Holding[]>([]); const [accountId, setAccountId] = useState('');
  const [symbol, setSymbol] = useState(''); const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState(''); const [fees, setFees] = useState('0.00');
  const [result, setResult] = useState<SaleAnalysis | null>(null); const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => { if (!token) return;
    try { const [a, h] = await Promise.all([apiRequest<Account[]>('/accounts', {}, token), apiRequest<Holding[]>('/holdings', {}, token)]); setAccounts(a); setHoldings(h); setError(''); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Could not load holdings.'); }
  }, [token]); useFocusEffect(useCallback(() => void refresh(), [refresh]));
  const choices = holdings.filter((x) => !accountId || x.investment_account_id === accountId);
  async function analyze() { if (!token || !accountId) { setError('Choose an investment account.'); return; }
    setBusy(true); setError(''); setResult(null);
    try { setResult(await apiRequest<SaleAnalysis>('/sale-analyses', { method: 'POST', headers: { 'Idempotency-Key': newIdempotencyKey() }, body: JSON.stringify({ investment_account_id: accountId, symbol, quantity, hypothetical_price: price, estimated_fees: fees, calculation_date: new Date().toISOString().slice(0, 10) }) }, token)); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Could not calculate estimate.'); }
    finally { setBusy(false); }
  }
  return <Screen><Text style={ui.title}>Hypothetical sale analysis</Text>
    <Text style={ui.subtitle}>Estimate only using your price input. No order will be placed and holdings will not change.</Text>
    {error ? <Text style={ui.error}>{error}</Text> : null}
    <Text style={ui.heading}>Investment account</Text><View style={ui.row}>{accounts.filter((x) => x.type === 'investment' && x.is_active).map((x) => <Choice key={x.id} label={x.name} selected={accountId === x.id} onPress={() => { setAccountId(x.id); setSymbol(''); }} />)}</View>
    <Text style={ui.heading}>Holding</Text><View style={ui.row}>{choices.map((x) => <Choice key={`${x.investment_account_id}-${x.symbol}`} label={`${x.symbol} (${x.quantity})`} selected={symbol === x.symbol} onPress={() => { setAccountId(x.investment_account_id); setSymbol(x.symbol); }} />)}</View>
    <Field label="Quantity" value={quantity} onChangeText={setQuantity} keyboardType="decimal-pad" />
    <Field label="Hypothetical price (PKR)" value={price} onChangeText={setPrice} keyboardType="decimal-pad" />
    <Field label="Estimated fees (PKR)" value={fees} onChangeText={setFees} keyboardType="decimal-pad" />
    <ActionButton title="Calculate estimate (no order)" onPress={() => void analyze()} disabled={busy} />
    {result ? <View style={ui.card}><Text style={ui.cardTitle}>Estimate only · no order placed</Text>
      <Text>Gross proceeds: {result.gross_proceeds} PKR</Text><Text>FIFO cost basis: {result.fifo_cost_basis} PKR</Text>
      <Text>Gross profit/loss: {result.gross_profit_loss} PKR</Text><Text>Estimated fees: {result.estimated_fees} PKR</Text>
      <Text>Estimated tax: {result.estimated_tax ?? 'not configured'}</Text>
      <Text style={ui.amount}>Net proceeds: {result.net_proceeds} PKR</Text><Text>Net profit/loss: {result.net_profit_loss} PKR</Text>
      <Text style={ui.muted}>Tax status: {result.tax_status}. Excludes: {result.excluded_items.join('; ')}.</Text>
    </View> : null}
  </Screen>;
}
