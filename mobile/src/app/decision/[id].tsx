import { useFocusEffect, useLocalSearchParams } from 'expo-router'; import { useCallback, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { ApiError, apiRequest, newIdempotencyKey } from '@/api'; import { useAuth } from '@/auth';
import { ActionButton, Choice, Field, Screen, ui } from '@/components'; import { DecisionDetail } from '@/types';

const checkNames = ['thesis_written_before_trade','risks_considered','concentration_considered','within_recorded_limits','followed_original_plan'] as const;
type CheckName = typeof checkNames[number];
export default function DecisionDetailScreen() {
  const { id } = useLocalSearchParams<{id:string}>(); const { token } = useAuth();
  const [detail,setDetail]=useState<DecisionDetail|null>(null); const [error,setError]=useState(''); const [busy,setBusy]=useState(false);
  const [happened,setHappened]=useState(''); const [held,setHeld]=useState(''); const [failed,setFailed]=useState(''); const [lessons,setLessons]=useState('');
  const [checks,setChecks]=useState<Record<CheckName,boolean|null>>({thesis_written_before_trade:null,risks_considered:null,concentration_considered:null,within_recorded_limits:null,followed_original_plan:null});
  const refresh=useCallback(async()=>{if(!token||!id)return; try{setDetail(await apiRequest<DecisionDetail>(`/decisions/${id}`,{},token));setError('');}catch(reason){setError(reason instanceof ApiError?reason.message:'Could not load decision.');}},[token,id]);
  useFocusEffect(useCallback(()=>{void refresh();},[refresh]));
  async function submit(){if(!token||!id)return;setBusy(true);setError('');try{await apiRequest(`/decisions/${id}/reviews`,{method:'POST',headers:{'Idempotency-Key':newIdempotencyKey()},body:JSON.stringify({what_happened:happened,assumptions_held:held,assumptions_failed:failed,lessons_learned:lessons,...checks})},token);setHappened('');setHeld('');setFailed('');setLessons('');await refresh();}catch(reason){setError(reason instanceof ApiError?reason.message:'Could not save review.');}finally{setBusy(false);}}
  if(!detail&&!error)return <ActivityIndicator style={{flex:1}}/>;
  const outcome=detail?.outcome;
  return <Screen>{error?<Text style={ui.error}>{error}</Text>:null}{detail?<><Text style={ui.title}>{detail.instrument} · {detail.action_considered}</Text>
    <Text style={ui.subtitle}>Original reasoning is preserved. Process quality is separate from financial outcome.</Text>
    <View style={ui.card}><Text style={ui.cardTitle}>Original thesis</Text><Text>{detail.rationale}</Text><Text>Goal: {detail.goal}</Text><Text>Risks: {detail.risk_factors}</Text><Text>Expected: {detail.expected_outcome}</Text></View>
    <View style={ui.card}><Text style={ui.cardTitle}>Recorded outcome</Text><Text>State: {String(outcome?.state)}</Text><Text>Gross: {String(outcome?.gross_result_before_fees_and_tax ?? outcome?.gross_result_before_tax ?? 'unavailable')}</Text><Text>Fees: {String(outcome?.fees ?? 'unavailable')}</Text><Text>Estimated tax: {String(outcome?.estimated_tax ?? 'not configured/unavailable')}</Text><Text>Net: {String(outcome?.net_result ?? 'unavailable')}</Text><Text style={ui.muted}>No current market value is invented. Informational only; no order was placed.</Text></View>
    <Text style={ui.heading}>Add append-only review</Text><Field label="What happened" value={happened} onChangeText={setHappened} multiline/><Field label="Assumptions that held" value={held} onChangeText={setHeld} multiline/><Field label="Assumptions that failed" value={failed} onChangeText={setFailed} multiline/><Field label="Lessons learned" value={lessons} onChangeText={setLessons} multiline/>
    {checkNames.map(name=><View key={name}><Text style={ui.muted}>{name.replaceAll('_',' ')}</Text><View style={ui.row}><Choice label="Yes" selected={checks[name]===true} onPress={()=>setChecks({...checks,[name]:true})}/><Choice label="No" selected={checks[name]===false} onPress={()=>setChecks({...checks,[name]:false})}/><Choice label="Unknown" selected={checks[name]===null} onPress={()=>setChecks({...checks,[name]:null})}/></View></View>)}
    <ActionButton title="Save review" onPress={()=>void submit()} disabled={busy}/><Text style={ui.heading}>Review history</Text>
    {detail.reviews.map(r=><View key={r.id} style={ui.card}><Text>{r.what_happened}</Text><Text>Lessons: {r.lessons_learned}</Text><Text>Process checklist: {r.process_snapshot.positive_count}/{r.process_snapshot.answered_count} documented yes</Text><Text style={ui.muted}>{r.process_snapshot.explanation} Financial outcome is excluded from this count.</Text></View>)}</>:null}</Screen>;
}
