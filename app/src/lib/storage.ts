import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

// SecureStore only works on iOS and Android. In a browser we use localStorage.
const isWeb = Platform.OS === 'web';

function webStore(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null; // blocked, for example in a private window
  }
}

export async function getItem(key: string): Promise<string | null> {
  try {
    if (isWeb) return webStore()?.getItem(key) ?? null;
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

export async function setItem(key: string, value: string): Promise<void> {
  try {
    if (isWeb) webStore()?.setItem(key, value);
    else await SecureStore.setItemAsync(key, value);
  } catch (e) {
    console.warn('could not save', key, e);
  }
}

export async function deleteItem(key: string): Promise<void> {
  try {
    if (isWeb) webStore()?.removeItem(key);
    else await SecureStore.deleteItemAsync(key);
  } catch {
    // nothing to delete
  }
}