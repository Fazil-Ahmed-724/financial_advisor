import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';

import { ApiError, apiRequest } from '@/api'; import { useAuth } from '@/auth';
import { ActionButton, Screen, ui } from '@/components'; import { Holding } from '@/types';

export default function HoldingsScreen() {
  const { token } = useAuth(); const [items, setItems] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    if (!token) return; setLoading(true);
    try { setItems(await apiRequest<Holding[]>('/holdings', {}, token)); setError(''); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Could not load holdings.'); }
    finally { setLoading(false); }
  }, [token]);
  useFocusEffect(useCallback(() => void refresh(), [refresh]));
  return <Screen><Text style={ui.title}>Holdings and FIFO lots</Text>
    <Text style={ui.subtitle}>Quantities and ledger book cost only. No current market prices.</Text>
    {error ? <Text style={ui.error}>{error}</Text> : null}{loading ? <ActivityIndicator /> : null}
    {!loading && items.length === 0 ? <Text style={ui.muted}>No open investment lots.</Text> : null}
    {items.map((item) => <View key={`${item.investment_account_id}-${item.symbol}`} style={ui.card}>
      <Text style={ui.cardTitle}>{item.symbol}</Text><Text>Quantity: {item.quantity}</Text>
      <Text style={ui.amount}>Book cost: {item.remaining_book_cost} PKR</Text>
      <Text>Realized gain/loss: {item.realized_gain_loss} PKR</Text>
      {item.lots.map((lot) => <Text style={ui.muted} key={lot.id}>FIFO lot {lot.acquired_on}: {lot.remaining_quantity} shares / {lot.remaining_cost} PKR</Text>)}
    </View>)}
    <ActionButton title="Refresh holdings" onPress={() => void refresh()} disabled={loading} />
  </Screen>;
}
