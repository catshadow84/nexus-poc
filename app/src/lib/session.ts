import { deleteItem, getItem, setItem } from '@/lib/storage';

const TOKEN_KEY = 'nexus.token';
const TRIP_KEY = 'nexus.trip';
const STAFF_KEY = 'nexus.staff';

// ---------- first-launch intro (kept when signing out) ----------

const WELCOME_KEY = 'nexus.welcome-seen';

export async function hasSeenWelcome(): Promise<boolean> {
  return (await getItem(WELCOME_KEY)) === '1';
}

export async function markWelcomeSeen(): Promise<void> {
  await setItem(WELCOME_KEY, '1');
}

// ---------- token (guest token, staff session token, or the old shared staff key) ----------

let cachedToken: string | null | undefined; // undefined = not loaded yet

export async function getToken(): Promise<string | null> {
  if (cachedToken !== undefined) return cachedToken;
  cachedToken = await getItem(TOKEN_KEY);
  return cachedToken;
}

export async function setToken(token: string): Promise<void> {
  cachedToken = token;
  await setItem(TOKEN_KEY, token);
}

/** Sign out completely: token, guest trip and staff profile. */
export async function clearToken(): Promise<void> {
  cachedToken = null;
  await deleteItem(TOKEN_KEY);
  await clearTrip();
  await clearStaff();
}

// ---------- guest trip ----------

export type Trip = { bookingId: string; guestId: string };
let cachedTrip: Trip | null | undefined;

export async function getTrip(): Promise<Trip | null> {
  if (cachedTrip !== undefined) return cachedTrip;
  try {
    const raw = await getItem(TRIP_KEY);
    cachedTrip = raw ? (JSON.parse(raw) as Trip) : null;
  } catch {
    cachedTrip = null;
  }
  return cachedTrip;
}

/** A trip means this phone is a guest's, so any staff profile is dropped. */
export async function setTrip(trip: Trip): Promise<void> {
  cachedTrip = trip;
  await setItem(TRIP_KEY, JSON.stringify(trip));
  await clearStaff();
}

export async function clearTrip(): Promise<void> {
  cachedTrip = null;
  await deleteItem(TRIP_KEY);
}

// ---------- staff profile (who is signed in, and their role) ----------

export type StaffRole = 'front_desk' | 'housekeeping' | 'maintenance' | 'manager';
export type StaffSession = { role: StaffRole; name: string; username: string };
let cachedStaff: StaffSession | null | undefined;

export async function getStaff(): Promise<StaffSession | null> {
  if (cachedStaff !== undefined) return cachedStaff;
  try {
    const raw = await getItem(STAFF_KEY);
    cachedStaff = raw ? (JSON.parse(raw) as StaffSession) : null;
  } catch {
    cachedStaff = null;
  }
  return cachedStaff;
}

export async function setStaff(staff: StaffSession): Promise<void> {
  cachedStaff = staff;
  await setItem(STAFF_KEY, JSON.stringify(staff));
  await clearTrip();
}

export async function clearStaff(): Promise<void> {
  cachedStaff = null;
  await deleteItem(STAFF_KEY);
}
