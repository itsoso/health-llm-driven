import * as SecureStore from 'expo-secure-store';
import api, { TOKEN_KEY } from './api';

export interface User {
  id: number;
  username: string;
  email?: string;
  nickname?: string;
  avatar_url?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export async function login(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/auth/login/json', {
    username,
    password,
  });
  await SecureStore.setItemAsync(TOKEN_KEY, data.access_token);
  return data;
}

export async function logout(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export async function getToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function isLoggedIn(): Promise<boolean> {
  const token = await getToken();
  return token !== null;
}

export async function fetchCurrentUser(): Promise<User> {
  const { data } = await api.get<User>('/auth/me');
  return data;
}
