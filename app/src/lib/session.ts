import * as SecureStore from 'expo-secure-store';

const KEY = 'nexus.token';
let cached: string | null | undefined; // undefined = not loaded yet

export async function getToken(): Promise<string | null> {
  if (cached !== undefined) return cached;
  try {
    cached = await SecureStore.getItemAsync(KEY);
  } catch {
    cached = null;
  }
  return cached;
}

export async function setToken(token: string): Promise<void> {
  cached = token;
  try {
    await SecureStore.setItemAsync(KEY, token);
  } catch (e) {
    console.warn('could not save token', e);
  }
}

export async function clearToken(): Promise<void> {
  cached = null;
  try {
    await SecureStore.deleteItemAsync(KEY);
  } catch {
    // nothing to delete
  }
}