import { useCallback, useState } from 'react';
import { Text, View, Pressable, ScrollView, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { api } from '@/lib/api';
import { clearToken, getTrip } from '@/lib/session';

type Booking = {
  id: string;
  room_id: string;
  status: string;
  planned_check_in: string | null;
  planned_check_out: string | null;
  apaleo_reservation_id: string | null;
};

const LABELS: Record<string, string> = {
  RESERVED: 'Reserved. Check in when you arrive.',
  CHECKED_IN: 'Checked in',
  CHECKED_OUT: 'Stay completed',
  CANCELED: 'Canceled',
  NO_SHOW: 'Marked as no-show',
};

export default function TripsScreen() {
  const [booking, setBooking] = useState<Booking | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const trip = await getTrip();
      if (!trip) {
        router.replace('/search');
        return;
      }
      setBooking(await api<Booking>(`/bookings/${trip.bookingId}`));
    } catch (e: any) {
      if (e.status === 401) {
        router.replace('/search');
        return;
      }
      setError(e.message ?? 'Could not load your trip');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function checkIn() {
    if (!booking) return;
    setBusy(true);
    try {
      await api(`/bookings/${booking.id}/checkin`, { method: 'POST' });
      router.replace('/');
    } catch (e: any) {
      Alert.alert('Check-in failed', e.message ?? 'Something went wrong');
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    await clearToken();
    router.replace('/search');
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.inner}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.subtitle}>MY TRIP</Text>

      {loading && <ActivityIndicator />}
      {error && <Text style={styles.err}>{error}</Text>}

      {booking && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{LABELS[booking.status] ?? booking.status}</Text>
          <Text style={styles.muted}>
            {booking.planned_check_in?.slice(0, 10)} → {booking.planned_check_out?.slice(0, 10)}
          </Text>
          <Text style={styles.muted}>Room: {booking.room_id}</Text>
          {booking.apaleo_reservation_id && (
            <Text style={styles.muted}>Reservation {booking.apaleo_reservation_id}</Text>
          )}

          {booking.status === 'RESERVED' && (
            <Pressable style={[styles.btn, busy && { opacity: 0.5 }]} onPress={checkIn} disabled={busy}>
              <Text style={styles.btnText}>{busy ? 'Checking in…' : 'Check in'}</Text>
            </Pressable>
          )}
          {booking.status === 'CHECKED_IN' && (
            <Pressable style={styles.btn} onPress={() => router.replace('/')}>
              <Text style={styles.btnText}>Open my room</Text>
            </Pressable>
          )}
          {booking.status === 'CHECKED_OUT' && (
            <Pressable style={styles.btn} onPress={() => router.push(`/summary?booking_id=${booking.id}`)}>
              <Text style={styles.btnText}>View receipt</Text>
            </Pressable>
          )}
        </View>
      )}

      <Pressable style={styles.secondary} onPress={load}>
        <Text style={styles.secondaryText}>Refresh</Text>
      </Pressable>
      <Pressable style={styles.secondary} onPress={() => router.push('/search')}>
        <Text style={styles.secondaryText}>Book another stay</Text>
      </Pressable>
      <Pressable onPress={signOut} style={{ marginTop: 24 }}>
        <Text style={styles.link}>Sign out</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: '#0a0a0a' },
  inner: { padding: 24, paddingTop: 72, paddingBottom: 64 },
  brand: { color: '#fff', fontSize: 36, fontWeight: 'bold', letterSpacing: 8 },
  subtitle: { color: '#888', marginTop: 8, marginBottom: 24, letterSpacing: 2 },
  card: { backgroundColor: '#141414', borderRadius: 14, padding: 16, marginBottom: 16 },
  cardTitle: { color: '#fff', fontSize: 18, fontWeight: '600' },
  muted: { color: '#888', marginTop: 4 },
  err: { color: '#f87171', marginVertical: 12 },
  btn: { backgroundColor: '#fff', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 16 },
  btnText: { color: '#000', fontWeight: '600', letterSpacing: 1 },
  secondary: { borderWidth: 1, borderColor: '#333', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 12 },
  secondaryText: { color: '#fff', letterSpacing: 1 },
  link: { color: '#8a94a3', textAlign: 'center', letterSpacing: 1 },
});