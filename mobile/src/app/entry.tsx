import { useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Text, View } from 'react-native';

import { ApiError, apiRequest, newIdempotencyKey } from '@/api';
import { useAuth } from '@/auth';
import { ActionButton, Choice, Field, Screen, ui } from '@/components';
import { Account, AccountBalance } from '@/types';

type EntryKind = 'opening' | 'income' | 'expense';

export default function EntryScreen() {
  const { token } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [balances, setBalances] = useState<AccountBalance[]>([]);
  const [kind, setKind] = useState<EntryKind>('opening');
  const [primaryId, setPrimaryId] = useState('');
  const [offsetId, setOffsetId] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!token) return;
    const [nextAccounts, nextBalances] = await Promise.all([
      apiRequest<Account[]>('/accounts', {}, token),
      apiRequest<AccountBalance[]>('/accounts/balances', {}, token),
    ]);
    setAccounts(nextAccounts.filter((account) => account.is_active));
    setBalances(nextBalances);
  }, [token]);
  useFocusEffect(useCallback(() => {
    void refresh().catch(() => setError('Could not load accounts.'));
  }, [refresh]));

  const primary = useMemo(() => accounts.filter((account) => {
    if (kind === 'opening') return ['cash', 'investment', 'liability'].includes(account.type);
    if (kind === 'income') return ['cash', 'investment'].includes(account.type);
    return account.type === 'expense';
  }), [accounts, kind]);
  const offsets = useMemo(() => accounts.filter((account) => {
    if (kind === 'opening') return account.type === 'equity';
    if (kind === 'income') return account.type === 'income';
    return ['cash', 'investment'].includes(account.type);
  }), [accounts, kind]);

  function selectKind(value: EntryKind) {
    setKind(value); setPrimaryId(''); setOffsetId(''); setMessage(''); setError('');
  }

  async function submit() {
    if (!token) return;
    const primaryAccount = accounts.find((account) => account.id === primaryId);
    const numeric = Number(amount);
    if (!primaryAccount || !offsetId || !Number.isFinite(numeric) || numeric <= 0 || !/^\d+(\.\d{1,2})?$/.test(amount)) {
      setError('Choose both accounts and enter a positive amount with up to two decimals.');
      return;
    }
    const formatted = numeric.toFixed(2);
    const primaryAmount = kind === 'opening' && primaryAccount.type === 'liability'
      ? `-${formatted}` : formatted;
    const offsetAmount = primaryAmount.startsWith('-') ? formatted : `-${formatted}`;
    setBusy(true); setError(''); setMessage('');
    try {
      await apiRequest('/journal-entries', {
        method: 'POST',
        headers: { 'Idempotency-Key': newIdempotencyKey() },
        body: JSON.stringify({
          kind,
          description: description || null,
          occurred_at: new Date().toISOString(),
          lines: [
            { account_id: primaryId, amount: primaryAmount },
            { account_id: offsetId, amount: offsetAmount },
          ],
        }),
      }, token);
      setAmount(''); setDescription('');
      setMessage('Entry recorded and balances refreshed.');
      await refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Could not record entry.');
    } finally { setBusy(false); }
  }

  return (
    <Screen>
      <Text style={ui.heading}>Entry type</Text>
      <View style={ui.row}>
        {(['opening', 'income', 'expense'] as EntryKind[]).map((value) => (
          <Choice key={value} label={value} selected={kind === value} onPress={() => selectKind(value)} />
        ))}
      </View>
      {error ? <Text style={ui.error}>{error}</Text> : null}
      {message ? <Text style={ui.success}>{message}</Text> : null}
      <Text style={ui.muted}>
        {kind === 'expense' ? 'Expense account' : kind === 'income' ? 'Receiving account' : 'Opening-balance account'}
      </Text>
      <View style={ui.row}>
        {primary.map((account) => (
          <Choice key={account.id} label={account.name} selected={primaryId === account.id} onPress={() => setPrimaryId(account.id)} />
        ))}
      </View>
      <Text style={ui.muted}>
        {kind === 'opening' ? 'Equity offset' : kind === 'income' ? 'Income account' : 'Paying account'}
      </Text>
      <View style={ui.row}>
        {offsets.map((account) => (
          <Choice key={account.id} label={account.name} selected={offsetId === account.id} onPress={() => setOffsetId(account.id)} />
        ))}
      </View>
      <Field label="Amount (PKR)" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0.00" />
      <Field label="Description (optional)" value={description} onChangeText={setDescription} maxLength={255} />
      <ActionButton title="Record balanced entry" onPress={() => void submit()} disabled={busy} />
      <Text style={ui.heading}>Updated balances</Text>
      {balances.map(({ account, balance }) => (
        <View key={account.id} style={ui.card}>
          <Text style={ui.cardTitle}>{account.name}</Text>
          <Text style={ui.amount}>{balance} PKR</Text>
        </View>
      ))}
    </Screen>
  );
}
