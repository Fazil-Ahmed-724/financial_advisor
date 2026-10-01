import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { apiRequest } from '@/api';
import { NotificationDevice } from '@/types';

const INSTALLATION_KEY='wealth-manager.installation-id';
export async function installationId(){
  let value=await SecureStore.getItemAsync(INSTALLATION_KEY);
  if(!value){value='xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=Math.floor(Math.random()*16);return (c==='x'?r:(r&3)|8).toString(16)});await SecureStore.setItemAsync(INSTALLATION_KEY,value);}
  return value;
}
export async function deviceCredentials(){return {installation_id:await installationId(),platform:Platform.OS==='ios'?'ios':'android',device_name:(Device.deviceName||`${Platform.OS} device`).slice(0,80)}}
export async function registerPush(token:string):Promise<NotificationDevice>{
  if(!Device.isDevice)throw new Error('Push registration requires a physical device and development build.');
  if(Platform.OS==='android')await Notifications.setNotificationChannelAsync('default',{name:'Informational updates',importance:Notifications.AndroidImportance.DEFAULT});
  let permission=await Notifications.getPermissionsAsync();
  if(permission.status!=='granted')permission=await Notifications.requestPermissionsAsync();
  if(permission.status!=='granted')throw new Error('Notification permission was denied. You can keep notifications disabled.');
  const projectId=process.env.EXPO_PUBLIC_EAS_PROJECT_ID;
  if(!projectId)throw new Error('EXPO_PUBLIC_EAS_PROJECT_ID is required for push registration.');
  const expoToken=(await Notifications.getExpoPushTokenAsync({projectId})).data;
  const credentials=await deviceCredentials();
  return apiRequest<NotificationDevice>('/notifications/devices',{method:'POST',body:JSON.stringify({...credentials,display_name:credentials.device_name,expo_push_token:expoToken,notifications_enabled:false})},token);
}
