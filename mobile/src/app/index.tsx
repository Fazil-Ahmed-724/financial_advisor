import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';

import { ApiError, apiRequest } from '@/api';
import { useAuth } from '@/auth';
import { ActionButton, Field, Screen, ui } from '@/components';
import { Dashboard, FinancialProfile } from '@/types';

export default function HomeScreen() {
  const { token, loading, login, register, logout } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [expenses, setExpenses] = useState('');
  const [months, setMonths] = useState('3');
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [message, setMessage] = useState('');

  const refresh = useCallback(async () => {
    if (!token) return;
    setDashboardLoading(true);
    try {
      const result = await apiRequest<Dashboard>('/dashboard', {}, token);
      setDashboard(result);
      setExpenses(result.monthly_essential_expenses);
      setMonths(String(result.reserve_months));
      setError('');
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Could not load balances.');
    } finally {
      setDashboardLoading(false);
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

  async function saveProfile() {
    if (!token) return;
    if (!/^\d+(\.\d{1,2})?$/.test(expenses) || !/^\d+$/.test(months)) {
      setError('Enter nonnegative expenses with up to two decimals and whole reserve months.');
      return;
    }
    const monthCount = Number(months);
    if (monthCount < 0 || monthCount > 24) {
      setError('Reserve months must be between 0 and 24.');
      return;
    }
    setBusy(true); setError(''); setMessage('');
    try {
      await apiRequest<FinancialProfile>('/financial-profile', {
        method: 'PUT',
        body: JSON.stringify({
          monthly_essential_expenses: expenses,
          reserve_months: monthCount,
        }),
      }, token);
      await refresh();
      setMessage('Emergency reserve settings saved.');
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Could not save settings.');
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
      <Text style={ui.title}>Financial dashboard</Text>
      <Text style={ui.subtitle}>All values are PKR. Investments and net worth use ledger/book value.</Text>
      <Link href="/accounts" asChild><ActionButton title="Manage accounts" onPress={() => {}} /></Link>
      <Link href="/entry" asChild><ActionButton title="Record entry" onPress={() => {}} /></Link>
      <Link href="/trade" asChild><ActionButton title="Record completed external trade" onPress={() => {}} /></Link>
      <Link href="/holdings" asChild><ActionButton title="Holdings and FIFO lots" onPress={() => {}} /></Link>
      <Link href="/analysis" asChild><ActionButton title="Hypothetical sale analysis" onPress={() => {}} /></Link>
      <Link href="/decisions" asChild><ActionButton title="Investment decision journal" onPress={() => {}} /></Link>
      <Link href="/books" asChild><ActionButton title="Personal financial book library" onPress={() => {}} /></Link>
      <Link href="/property" asChild><ActionButton title="Karachi property research" onPress={() => {}} /></Link>
      {error ? <Text style={ui.error}>{error}</Text> : null}
      {message ? <Text style={ui.success}>{message}</Text> : null}
      {dashboardLoading ? <ActivityIndicator /> : null}
      {!dashboardLoading && !dashboard ? <Text style={ui.muted}>Dashboard data is unavailable.</Text> : null}
      {dashboard ? (
        <>
          <View style={ui.card}><Text style={ui.cardTitle}>Cash</Text><Text style={ui.amount}>{dashboard.cash_balance} PKR</Text></View>
          <View style={ui.card}><Text style={ui.cardTitle}>Investments · book value</Text><Text style={ui.amount}>{dashboard.investment_book_value} PKR</Text><Text style={ui.muted}>Current market value is unavailable.</Text></View>
          <View style={ui.card}><Text style={ui.cardTitle}>Liabilities</Text><Text style={ui.amount}>{dashboard.liability_balance} PKR</Text></View>
          <View style={ui.card}><Text style={ui.cardTitle}>Net worth · book value</Text><Text style={ui.amount}>{dashboard.net_worth_book_value} PKR</Text></View>
          <View style={ui.card}><Text style={ui.cardTitle}>Confirmed owned property</Text><Text style={ui.amount}>{dashboard.confirmed_property_value} PKR</Text><Text style={ui.muted}>User-confirmed valuation only. Property remains separate from cash and investable cash.</Text></View>
          <View style={ui.card}><Text style={ui.cardTitle}>Net worth including confirmed property</Text><Text style={ui.amount}>{dashboard.net_worth_with_confirmed_property} PKR</Text></View>
          <View style={ui.card}><Text style={ui.cardTitle}>Emergency reserve target</Text><Text style={ui.amount}>{dashboard.reserve_target} PKR</Text><Text style={ui.muted}>{dashboard.reserve_months} months × {dashboard.monthly_essential_expenses} PKR</Text></View>
          <View style={ui.card}><Text style={ui.cardTitle}>Protected emergency cash</Text><Text style={ui.amount}>{dashboard.protected_emergency_cash} PKR</Text></View>
          <View style={ui.card}><Text style={ui.cardTitle}>Investable cash</Text><Text style={ui.amount}>{dashboard.investable_cash} PKR</Text><Text style={ui.muted}>After protected reserve and ledger liabilities; never below zero.</Text></View>
          {dashboard.cash_balance === '0.00' && dashboard.investment_book_value === '0.00' && dashboard.liability_balance === '0.00'
            ? <Text style={ui.muted}>No ledger balances yet. Create accounts and record an opening balance.</Text> : null}
        </>
      ) : null}
      <Text style={ui.heading}>Emergency reserve settings</Text>
      <Field label="Monthly essential expenses (PKR)" value={expenses} onChangeText={setExpenses} keyboardType="decimal-pad" placeholder="0.00" />
      <Field label="Reserve months (0–24)" value={months} onChangeText={setMonths} keyboardType="number-pad" placeholder="3" />
      <ActionButton title="Save reserve settings" onPress={() => void saveProfile()} disabled={busy} />
      <ActionButton title="Refresh dashboard" onPress={() => void refresh()} disabled={dashboardLoading} />
      <ActionButton title="Sign out" onPress={() => void logout()} />
    </Screen>
  );
}
