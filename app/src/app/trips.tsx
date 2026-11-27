import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { api } from '@/lib/api';
import { light } from '@/lib/brand';
import { groupPin, nightsBetween, prettyDate, prettyMoment } from '@/lib/dates';
import { heroPhoto } from '@/lib/rooms';
import { clearToken, getTrip } from '@/lib/session';
import {
  GBanner,
  GCard,
  GhostButton,
  GScreen,
  PrimaryButton,
  TopBar,
} from '@/components/guest-ui';

type Booking = {
  id: string;
  room_id: string;
  status: string;
  planned_check_in: string | null;
  planned_check_out: string | null;
  apaleo_reservation_id: string | null;
  door_pin?: string | null;
  door_pin_expires?: string | null;
};

const STATUS: Record<string, { label: string; hint: string; color: string; bg: string }> = {
  RESERVED: {
    label: 'Reserved',
    hint: 'Check in when you arrive.',
    color: '#9A5B00',
    bg: '#FFF1D9',
  },
  CHECKED_IN: {
    label: 'Checked in',
    hint: 'Your room is ready. Enjoy your stay.',
    color: light.ok,
    bg: '#DDF3EA',
  },
  CHECKED_OUT: {
    label: 'Stay completed',
    hint: 'Thank you for staying with us.',
    color: light.muted,
    bg: light.soft,
  },
  CANCELED: { label: 'Canceled', hint: 'This reservation was canceled.', color: light.danger, bg: light.dangerSoft },
  NO_SHOW: { label: 'No-show', hint: 'This reservation was marked as a no-show.', color: light.danger, bg: light.dangerSoft },
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
    setError(null);
    try {
      await api(`/bookings/${booking.id}/checkin`, { method: 'POST' });
      router.replace('/');
    } catch (e: any) {
      setError(e.message ?? 'Check-in failed. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  function confirmCancel() {
    Alert.alert(
      'Cancel this reservation?',
      'This cannot be undone. A cancellation fee may apply on some rates.',
      [
        { text: 'Keep it', style: 'cancel' },
        { text: 'Cancel reservation', style: 'destructive', onPress: doCancel },
      ],
    );
  }

  async function doCancel() {
    if (!booking) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/bookings/${booking.id}/cancel`, { method: 'POST' });
      await load();
    } catch (e: any) {
      setError(e.message ?? 'Could not cancel. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    await clearToken();
    router.replace('/search');
  }

  const arrive = booking?.planned_check_in?.slice(0, 10);
  const depart = booking?.planned_check_out?.slice(0, 10);
  const nights = arrive && depart ? nightsBetween(arrive, depart) : null;
  const status = booking ? (STATUS[booking.status] ?? { label: booking.status, hint: '', color: light.muted, bg: light.soft }) : null;

  return (
    <GScreen>
      <TopBar />
      <Text style={styles.title}>My trip</Text>

      {loading && !booking && <ActivityIndicator style={{ marginTop: 32 }} color={light.navy} />}
      {error && <GBanner text={error} />}

      {booking && status && (
        <GCard style={{ padding: 0 }}>
          <Image source={heroPhoto} style={styles.photo} resizeMode="cover" />
          <View style={{ padding: 16 }}>
            <View style={[styles.chip, { backgroundColor: status.bg }]}>
              <Text style={[styles.chipText, { color: status.color }]}>{status.label}</Text>
            </View>
            {status.hint ? <Text style={styles.hint}>{status.hint}</Text> : null}

            <View style={styles.divider} />
            {arrive && <Row label="Arrive" value={prettyDate(arrive)} />}
            {depart && <Row label="Depart" value={prettyDate(depart)} />}
            {nights != null && <Row label="Nights" value={String(nights)} />}
            <Row label="Room" value={booking.room_id.replace(/^room\s*/i, 'Room ')} />
            {booking.apaleo_reservation_id && (
              <Row label="Reservation" value={booking.apaleo_reservation_id} />
            )}

            {booking.status === 'CHECKED_IN' && booking.door_pin && (
              <View style={styles.pinBox}>
                <Text style={styles.pinLabel}>Your door code</Text>
                <Text style={styles.pin}>{groupPin(booking.door_pin)}</Text>
                {booking.door_pin_expires && (
                  <Text style={styles.pinNote}>
                    Works until {prettyMoment(booking.door_pin_expires)}. Type it on the door keypad.
                  </Text>
                )}
              </View>
            )}

            <View style={{ marginTop: 16, gap: 10 }}>
              {booking.status === 'RESERVED' && (
                <>
                  <PrimaryButton
                    label={busy ? 'Checking in…' : 'Check in'}
                    onPress={checkIn}
                    disabled={busy}
                  />
                  <GhostButton label="Cancel reservation" onPress={confirmCancel} />
                </>
              )}
              {booking.status === 'CHECKED_IN' && (
                <PrimaryButton label="Open my room" onPress={() => router.replace('/')} />
              )}
              {booking.status === 'CHECKED_OUT' && (
                <PrimaryButton
                  label="View receipt"
                  onPress={() => router.push(`/summary?booking_id=${booking.id}`)}
                />
              )}
            </View>
          </View>
        </GCard>
      )}

      <View style={{ marginTop: 18, gap: 10 }}>
        <GhostButton label="Book another stay" onPress={() => router.push('/search')} />
        <GhostButton label="Profile" onPress={() => router.push('/profile')} />
        <GhostButton label="Refresh" onPress={load} />
      </View>

      <Pressable onPress={signOut} accessibilityRole="button" style={styles.signOut}>
        <Text style={styles.signOutText}>Sign out</Text>
      </Pressable>
    </GScreen>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  title: { color: light.ink, fontSize: 30, fontWeight: '800' },
  photo: { width: '100%', height: 160 },
  chip: { alignSelf: 'flex-start', borderRadius: 999, paddingVertical: 5, paddingHorizontal: 12 },
  chipText: { fontSize: 13, fontWeight: '800' },
  hint: { color: light.muted, fontSize: 15, marginTop: 10, lineHeight: 22 },
  divider: { height: 1, backgroundColor: light.line, marginVertical: 14 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5, gap: 12 },
  rowLabel: { color: light.muted, fontSize: 15 },
  rowValue: { color: light.ink, fontSize: 15, fontWeight: '600', flexShrink: 1, textAlign: 'right' },
  pinBox: {
    marginTop: 14,
    backgroundColor: light.soft,
    borderRadius: 14,
    padding: 14,
    alignItems: 'center',
  },
  pinLabel: { color: light.muted, fontSize: 13, fontWeight: '700', letterSpacing: 0.5 },
  pin: { color: light.navy, fontSize: 36, fontWeight: '800', letterSpacing: 4, marginTop: 4 },
  pinNote: { color: light.muted, fontSize: 13, marginTop: 6, textAlign: 'center' },
  signOut: { alignSelf: 'center', paddingVertical: 20, paddingHorizontal: 20 },
  signOutText: { color: light.muted, fontSize: 15, fontWeight: '600' },
});
