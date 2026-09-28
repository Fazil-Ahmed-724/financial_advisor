import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';

import { ApiError, apiRequest, newIdempotencyKey } from '@/api';
import { useAuth } from '@/auth';
import { ActionButton, Choice, Field, Screen, ui } from '@/components';
import { Account, AccountType } from '@/types';

const accountTypes: AccountType[] = [
  'cash', 'investment', 'income', 'expense', 'liability', 'equity',
];

export default function AccountsScreen() {
  const { token } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [name, setName] = useState('');
  const [type, setType] = useState<AccountType>('cash');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (token) setAccounts(await apiRequest<Account[]>('/accounts', {}, token));
  }, [token]);
  useFocusEffect(useCallback(() => {
    void refresh().catch(() => setError('Could not load accounts.'));
  }, [refresh]));

  async function submit() {
    if (!token) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await apiRequest<Account>('/accounts', {
        method: 'POST',
        headers: { 'Idempotency-Key': newIdempotencyKey() },
        body: JSON.stringify({ name, type, currency: 'PKR' }),
      }, token);
      setName(''); setMessage('Account created.'); await refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Could not create account.');
    } finally { setBusy(false); }
  }

  return (
    <Screen>
      <Text style={ui.heading}>New account</Text>
      {error ? <Text style={ui.error}>{error}</Text> : null}
      {message ? <Text style={ui.success}>{message}</Text> : null}
      <Field label="Account name" value={name} onChangeText={setName} maxLength={100} />
      <Text style={ui.muted}>Account type</Text>
      <View style={ui.row}>
        {accountTypes.map((value) => (
          <Choice key={value} label={value} selected={type === value} onPress={() => setType(value)} />
        ))}
      </View>
      <ActionButton title="Create PKR account" onPress={() => void submit()} disabled={busy || !name.trim()} />
      <Text style={ui.heading}>Your accounts</Text>
      {accounts.map((account) => (
        <View key={account.id} style={ui.card}>
          <Text style={ui.cardTitle}>{account.name}</Text>
          <Text style={ui.muted}>{account.type} · {account.currency}</Text>
        </View>
      ))}
    </Screen>
  );
}
