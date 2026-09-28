import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';

import { ApiError, apiRequest } from '@/api';
import { useAuth } from '@/auth';
import { ActionButton, Field, Screen, ui } from '@/components';
import { AccountBalance } from '@/types';

export default function HomeScreen() {
  const { token, loading, login, register, logout } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [balances, setBalances] = useState<AccountBalance[]>([]);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      setBalances(await apiRequest<AccountBalance[]>('/accounts/balances', {}, token));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Could not load balances.');
    }
  }, [token]);
  useFocusEffect(useCallback(() => void refresh(), [refresh]));

  async function authenticate(mode: 'login' | 'register') {
    setBusy(true); setError('');
    try {
      await (mode === 'login' ? login(email, password) : register(email, password));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Authentication failed.');
    } finally { setBusy(false); }
  }

  if (loading) return <ActivityIndicator style={{ flex: 1 }} />;
  if (!token) return (
    <Screen>
      <Text style={ui.title}>Personal AI Wealth Manager</Text>
      <Text style={ui.subtitle}>Sign in to manage your PKR accounts and journal.</Text>
      {error ? <Text style={ui.error}>{error}</Text> : null}
      <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry />
      <ActionButton title="Sign in" onPress={() => void authenticate('login')} disabled={busy} />
      <ActionButton title="Create login" onPress={() => void authenticate('register')} disabled={busy} />
    </Screen>
  );

  return (
    <Screen>
      <Text style={ui.title}>Balances</Text>
      <Link href="/accounts" asChild><ActionButton title="Manage accounts" onPress={() => {}} /></Link>
      <Link href="/entry" asChild><ActionButton title="Record entry" onPress={() => {}} /></Link>
      {error ? <Text style={ui.error}>{error}</Text> : null}
      {balances.length === 0 ? <Text style={ui.muted}>Create accounts to begin.</Text> : balances.map(({ account, balance }) => (
        <View key={account.id} style={ui.card}>
          <Text style={ui.cardTitle}>{account.name}</Text>
          <Text style={ui.muted}>{account.type} · {account.currency}</Text>
          <Text style={ui.amount}>{balance} PKR</Text>
        </View>
      ))}
      <ActionButton title="Refresh balances" onPress={() => void refresh()} />
      <ActionButton title="Sign out" onPress={() => void logout()} />
    </Screen>
  );
}
