import { router, Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from '@/auth';
import * as Notifications from 'expo-notifications';
import { useEffect } from 'react';
import { notificationRoute } from '@/notification-routing';

function NotificationNavigation(){const{token}=useAuth();useEffect(()=>{const open=(response:Notifications.NotificationResponse|null)=>{const route=notificationRoute(response?.notification.request.content.data,Boolean(token));if(route)router.push(route as never)};Notifications.getLastNotificationResponseAsync().then(open);const subscription=Notifications.addNotificationResponseReceivedListener(open);return()=>subscription.remove()},[token]);return null}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <NotificationNavigation />
        <Stack>
          <Stack.Screen name="index" options={{ title: 'Wealth Manager' }} />
          <Stack.Screen name="accounts" options={{ title: 'Accounts' }} />
          <Stack.Screen name="entry" options={{ title: 'Record entry' }} />
          <Stack.Screen name="trade" options={{ title: 'Record external trade' }} />
          <Stack.Screen name="holdings" options={{ title: 'Holdings and FIFO lots' }} />
          <Stack.Screen name="analysis" options={{ title: 'Hypothetical sale' }} />
          <Stack.Screen name="decisions" options={{ title: 'Decision journal' }} />
          <Stack.Screen name="decision/[id]" options={{ title: 'Decision review' }} />
          <Stack.Screen name="books" options={{ title: 'Financial book library' }} />
          <Stack.Screen name="property" options={{ title: 'Karachi property research' }} />
          <Stack.Screen name="marketplace" options={{ title: 'Marketplace research' }} />
          <Stack.Screen name="inventory" options={{ title: 'Resale outcomes' }} />
          <Stack.Screen name="rankings" options={{ title: 'Marketplace Rankings' }} />
          <Stack.Screen name="product/[id]" options={{ title: 'Product Intelligence' }} />
          <Stack.Screen name="product-compare" options={{ title: 'Product Comparison' }} />
          <Stack.Screen name="watchlist" options={{ title: 'Product Watchlist' }} />
          <Stack.Screen name="marketplace-import" options={{ title: 'Import marketplace evidence' }} />
          <Stack.Screen name="match-review" options={{ title: 'Review imported matches' }} />
          <Stack.Screen name="assistant" options={{ title: 'Cited research assistant' }} />
          <Stack.Screen name="assistant-evidence" options={{ title: 'Assistant evidence and limitations' }} />
          <Stack.Screen name="assistant-feedback" options={{ title: 'Assistant feedback review' }} />
          <Stack.Screen name="notification-settings" options={{ title: 'Notifications and devices' }} />
          <Stack.Screen name="psx-research" options={{ title: 'PSX historical research' }} />
        </Stack>
        <StatusBar style="dark" />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
