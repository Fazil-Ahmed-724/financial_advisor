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
        </Stack>
        <StatusBar style="dark" />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
