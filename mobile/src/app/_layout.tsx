import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '@/auth';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
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
        </Stack>
        <StatusBar style="dark" />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
