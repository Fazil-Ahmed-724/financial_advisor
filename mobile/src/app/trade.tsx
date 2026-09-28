import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';

import { ApiError, apiRequest, newIdempotencyKey } from '@/api';
import { useAuth } from '@/auth';
import { ActionButton, Choice, Field, Screen, ui } from '@/components';
import { Account, InvestmentTrade } from '@/types';

export default function TradeScreen() {
  const { token } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [symbol, setSymbol] = useState(''); const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState(''); const [fees, setFees] = useState('0.00');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [investmentId, setInvestmentId] = useState(''); const [cashId, setCashId] = useState('');
  const [reference, setReference] = useState(''); const [error, setError] = useState('');
  const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!token) return;
    try { setAccounts(await apiRequest<Account[]>('/accounts', {}, token)); setError(''); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Could not load accounts.'); }
  }, [token]);
  useFocusEffect(useCallback(() => void refresh(), [refresh]));
  const investments = accounts.filter((x) => x.type === 'investment' && x.is_active);
  const cash = accounts.filter((x) => x.type === 'cash' && x.is_active);

  async function submit() {
    if (!token || !investmentId || !cashId) { setError('Choose an investment and cash account.'); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await apiRequest<InvestmentTrade>('/investment-trades', {
        method: 'POST', headers: { 'Idempotency-Key': newIdempotencyKey() },
        body: JSON.stringify({ side, symbol, trade_date: date, quantity,
          execution_price: price, fees, investment_account_id: investmentId,
          cash_account_id: cashId, external_reference: reference || null }),
      }, token);
      setMessage(`Recorded external ${result.side} transaction. No order was placed.`);
      setQuantity(''); setPrice('');
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Could not record external trade.'); }
    finally { setBusy(false); }
  }

  return <Screen>
    <Text style={ui.title}>Recorded external transaction</Text>
    <Text style={ui.subtitle}>Enter a trade already executed elsewhere. This app does not place orders.</Text>
    {error ? <Text style={ui.error}>{error}</Text> : null}{message ? <Text style={ui.success}>{message}</Text> : null}
    <View style={ui.row}>{(['BUY', 'SELL'] as const).map((x) => <Choice key={x} label={x} selected={side === x} onPress={() => setSide(x)} />)}</View>
    <Field label="Symbol" value={symbol} onChangeText={setSymbol} autoCapitalize="characters" placeholder="ABC" />
    <Field label="Trade date (YYYY-MM-DD)" value={date} onChangeText={setDate} />
    <Field label="Quantity" value={quantity} onChangeText={setQuantity} keyboardType="decimal-pad" />
    <Field label="Execution price (PKR)" value={price} onChangeText={setPrice} keyboardType="decimal-pad" />
    <Field label="Fees (PKR)" value={fees} onChangeText={setFees} keyboardType="decimal-pad" />
    <Text style={ui.heading}>Investment account</Text><View style={ui.row}>{investments.map((x) => <Choice key={x.id} label={x.name} selected={investmentId === x.id} onPress={() => setInvestmentId(x.id)} />)}</View>
    <Text style={ui.heading}>Cash account</Text><View style={ui.row}>{cash.map((x) => <Choice key={x.id} label={x.name} selected={cashId === x.id} onPress={() => setCashId(x.id)} />)}</View>
    <Field label="Broker/reference note (optional)" value={reference} onChangeText={setReference} maxLength={255} />
    <ActionButton title="Record completed external transaction" onPress={() => void submit()} disabled={busy} />
  </Screen>;
}
