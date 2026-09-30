import * as DocumentPicker from 'expo-document-picker';
import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { ApiError, apiRequest } from '@/api';
import { useAuth } from '@/auth';
import { ActionButton, Choice, Screen, ui } from '@/components';
import { MarketplaceImportBatch } from '@/types';

const kinds = ['product_observations','sourcing_options','competition_observations'] as const;
export default function MarketplaceImport(){
  const {token}=useAuth(); const [kind,setKind]=useState<typeof kinds[number]>('product_observations'); const [file,setFile]=useState<DocumentPicker.DocumentPickerAsset|null>(null); const [batches,setBatches]=useState<MarketplaceImportBatch[]>([]); const [error,setError]=useState(''); const [message,setMessage]=useState('');
  const refresh=useCallback(async()=>{if(!token)return;try{setBatches(await apiRequest('/api/v1/marketplace/imports',{},token));setError('');}catch(e){setError(e instanceof ApiError?e.message:'Could not load imports.');}},[token]);
  useFocusEffect(useCallback(()=>{void refresh();},[refresh]));
  async function pick(){const result=await DocumentPicker.getDocumentAsync({type:['text/csv','application/json','text/plain'],copyToCacheDirectory:true});if(!result.canceled)setFile(result.assets[0]);}
  async function upload(){if(!token||!file){setError('Select a CSV or JSON file first.');return;}const form=new FormData();form.append('import_type',kind);form.append('source_classification','authorized_export');form.append('file',{uri:file.uri,name:file.name,type:file.mimeType||'application/octet-stream'} as unknown as Blob);try{const batch=await apiRequest<MarketplaceImportBatch>('/api/v1/marketplace/imports',{method:'POST',body:form},token);setMessage(`Parsed ${batch.total_rows} rows. Review every invalid or uncertain row before commit.`);setFile(null);await refresh();}catch(e){setError(e instanceof ApiError?e.message:'Import failed.');}}
  return <Screen><Text style={ui.title}>Import marketplace evidence</Text><Text style={ui.subtitle}>CSV/JSON only. Imported facts stay as observations, sourcing, or competition evidence. Scores and margins are recalculated by the app.</Text>{error?<Text style={ui.error}>{error}</Text>:null}{message?<Text style={ui.success}>{message}</Text>:null}<View style={ui.row}>{kinds.map(x=><Choice key={x} label={x.replaceAll('_',' ')} selected={kind===x} onPress={()=>setKind(x)}/>)}</View><ActionButton title={file?`Selected: ${file.name}`:'Select CSV or JSON'} onPress={()=>void pick()}/><ActionButton title="Upload for preview" onPress={()=>void upload()}/><Text style={ui.heading}>Import history</Text>{batches.length===0?<Text style={ui.muted}>No import batches.</Text>:batches.map(b=><View style={ui.card} key={b.id}><Text style={ui.cardTitle}>{b.original_filename}</Text><Text>{b.import_type} · {b.status}</Text><Text>{b.valid_rows} valid · {b.invalid_rows} invalid · {b.warning_rows} warnings</Text><Link href={{pathname:'/match-review',params:{batchId:b.id}}} asChild><ActionButton title="Preview and review matches" onPress={()=>{}}/></Link></View>)}</Screen>;
}
