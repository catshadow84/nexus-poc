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
    await clearTrip();
}

const TRIP_KEY = 'nexus.trip';
export type Trip = { bookingId: string; guestId: string };
let cachedTrip: Trip | null | undefined;

export async function getTrip(): Promise<Trip | null> {
  if (cachedTrip !== undefined) return cachedTrip;
  try {
    const raw = await SecureStore.getItemAsync(TRIP_KEY);
    cachedTrip = raw ? (JSON.parse(raw) as Trip) : null;
  } catch {
    cachedTrip = null;
  }
  return cachedTrip;
}

export async function setTrip(trip: Trip): Promise<void> {
  cachedTrip = trip;
  try {
    await SecureStore.setItemAsync(TRIP_KEY, JSON.stringify(trip));
  } catch (e) {
    console.warn('could not save trip', e);
  }
}

export async function clearTrip(): Promise<void> {
  cachedTrip = null;
  try {
    await SecureStore.deleteItemAsync(TRIP_KEY);
  } catch {
    // nothing to delete
  }
}