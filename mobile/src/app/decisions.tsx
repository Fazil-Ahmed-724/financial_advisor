import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { ApiError, apiRequest, newIdempotencyKey } from '@/api'; import { useAuth } from '@/auth';
import { ActionButton, Choice, Field, Screen, ui } from '@/components';
import { Decision, InvestmentTrade, SaleAnalysis } from '@/types';

export default function DecisionsScreen() {
  const { token } = useAuth(); const [items, setItems] = useState<Decision[]>([]);
  const [trades, setTrades] = useState<InvestmentTrade[]>([]); const [analyses, setAnalyses] = useState<SaleAnalysis[]>([]);
  const [instrument, setInstrument] = useState(''); const [action, setAction] = useState<'BUY'|'SELL'|'HOLD'|'AVOID'>('BUY');
  const [rationale, setRationale] = useState(''); const [goal, setGoal] = useState('');
  const [period, setPeriod] = useState(''); const [risks, setRisks] = useState('');
  const [expected, setExpected] = useState(''); const [confidence, setConfidence] = useState('');
  const [reviewDate, setReviewDate] = useState(''); const [exit, setExit] = useState('');
  const [tradeId, setTradeId] = useState(''); const [analysisId, setAnalysisId] = useState('');
  const [error, setError] = useState(''); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => { if (!token) return;
    try { const [d,t,a] = await Promise.all([apiRequest<Decision[]>('/decisions',{},token), apiRequest<InvestmentTrade[]>('/investment-trades',{},token), apiRequest<SaleAnalysis[]>('/sale-analyses',{},token)]); setItems(d); setTrades(t); setAnalyses(a); setError(''); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Could not load decisions.'); }
  }, [token]); useFocusEffect(useCallback(() => void refresh(), [refresh]));
  async function submit() { if (!token) return; setBusy(true); setError(''); setMessage('');
    try { await apiRequest('/decisions',{method:'POST',headers:{'Idempotency-Key':newIdempotencyKey()},body:JSON.stringify({
      trade_id: tradeId || null, sale_analysis_id: analysisId || null, decision_date:new Date().toISOString().slice(0,10),
      instrument, action_considered:action, rationale, goal, expected_holding_period:period,
      risk_factors:risks, expected_outcome:expected, confidence:confidence || null,
      planned_review_date:reviewDate || null, exit_conditions:exit || null})},token);
      setMessage('Original decision snapshot saved.'); setRationale(''); await refresh();
    } catch(reason) { setError(reason instanceof ApiError ? reason.message : 'Could not save decision.'); }
    finally { setBusy(false); }
  }
  function linkTrade(t: InvestmentTrade) { setTradeId(t.id); setAnalysisId(''); setInstrument(t.symbol); setAction(t.side); }
  function linkAnalysis(a: SaleAnalysis) { setAnalysisId(a.id); setTradeId(''); setInstrument(a.symbol); setAction('SELL'); }
  return <Screen><Text style={ui.title}>Investment decision journal</Text>
    <Text style={ui.subtitle}>Save the reasoning snapshot before or alongside a trade recorded from elsewhere. This app did not place the trade.</Text>
    {error?<Text style={ui.error}>{error}</Text>:null}{message?<Text style={ui.success}>{message}</Text>:null}
    <Text style={ui.heading}>Optional recorded-trade link</Text><View style={ui.row}>{trades.map(t=><Choice key={t.id} label={`${t.side} ${t.symbol} ${t.trade_date}`} selected={tradeId===t.id} onPress={()=>linkTrade(t)}/>)}</View>
    <Text style={ui.heading}>Optional hypothetical-analysis link</Text><View style={ui.row}>{analyses.map(a=><Choice key={a.id} label={`${a.symbol} estimate`} selected={analysisId===a.id} onPress={()=>linkAnalysis(a)}/>)}</View>
    <Field label="Instrument" value={instrument} onChangeText={setInstrument} autoCapitalize="characters" />
    <View style={ui.row}>{(['BUY','SELL','HOLD','AVOID'] as const).map(x=><Choice key={x} label={x} selected={action===x} onPress={()=>setAction(x)}/>)}</View>
    <Field label="Rationale" value={rationale} onChangeText={setRationale} multiline />
    <Field label="Goal" value={goal} onChangeText={setGoal} /><Field label="Expected holding period" value={period} onChangeText={setPeriod} />
    <Field label="Risk factors considered" value={risks} onChangeText={setRisks} multiline />
    <Field label="Expected outcome" value={expected} onChangeText={setExpected} multiline />
    <Field label="Confidence 0–100 (optional)" value={confidence} onChangeText={setConfidence} keyboardType="decimal-pad" />
    <Field label="Planned review date YYYY-MM-DD (optional)" value={reviewDate} onChangeText={setReviewDate} />
    <Field label="Exit conditions (optional)" value={exit} onChangeText={setExit} multiline />
    <ActionButton title="Save original reasoning snapshot" onPress={()=>void submit()} disabled={busy}/>
    <Text style={ui.heading}>Saved decisions</Text>{items.length===0?<Text style={ui.muted}>No decisions recorded.</Text>:null}
    {items.map(d=><Link key={d.id} href={{pathname:'/decision/[id]',params:{id:d.id}}} asChild><ActionButton title={`${d.instrument} · ${d.action_considered} · ${d.decision_date}`} onPress={()=>{}}/></Link>)}
  </Screen>;
}
