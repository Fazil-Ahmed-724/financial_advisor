import * as SecureStore from 'expo-secure-store';
import {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { apiRequest } from '@/api';
import { TokenResponse } from '@/types';
import { deviceCredentials, installationId } from '@/notifications';

const TOKEN_KEY = 'wealth-manager.access-token';

type AuthContextValue = {
  token: string | null;
  loading: boolean;
  login(email: string, password: string): Promise<void>;
  register(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    SecureStore.getItemAsync(TOKEN_KEY)
      .then(setToken)
      .finally(() => setLoading(false));
  }, []);

  const saveToken = useCallback(async (value: string) => {
    await SecureStore.setItemAsync(TOKEN_KEY, value, {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
    setToken(value);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const device=await deviceCredentials();
    const result = await apiRequest<TokenResponse>('/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password, ...device }),
    });
    await saveToken(result.access_token);
  }, [saveToken]);

  const register = useCallback(async (email: string, password: string) => {
    const device=await deviceCredentials();
    const result = await apiRequest<{ token: TokenResponse }>('/auth/register', {
      method: 'POST', body: JSON.stringify({ email, password, ...device }),
    });
    await saveToken(result.token.access_token);
  }, [saveToken]);

  const logout = useCallback(async () => {
    if(token){try{const devices=await apiRequest<{id:string;installation_id:string}[]>('/notifications/devices',{},token);const currentInstallation=await installationId();const current=devices.find(x=>x.installation_id===currentInstallation);if(current)await apiRequest(`/notifications/devices/${current.id}`,{method:'DELETE'},token);}catch{/* Local logout still succeeds if revocation cannot reach the API. */}}
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    setToken(null);
  }, [token]);

  const value = useMemo(
    () => ({ token, loading, login, register, logout }),
    [token, loading, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
