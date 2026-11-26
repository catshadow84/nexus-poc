import { useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { api } from '@/lib/api';
import { light } from '@/lib/brand';
import { money, prettyDate } from '@/lib/dates';
import { roomPhoto } from '@/lib/rooms';
import { setToken, setTrip } from '@/lib/session';
import {
  GBanner,
  GCard,
  GField,
  GScreen,
  PrimaryButton,
  TopBar,
} from '@/components/guest-ui';

type Created = { id: string; guest_id: string; guest_token: string };

export default function ReserveScreen() {
  const p = useLocalSearchParams<{
    arrival: string;
    departure: string;
    nights: string;
    adults: string;
    rate_plan_id: string;
    room_type: string;
    rate_plan: string;
    total: string;
    currency: string;
  }>();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nights = Number(p.nights) || 1;
  const adults = Number(p.adults) || 1;
  const total = money(Number(p.total), p.currency ?? '');

  async function confirm() {
    const cleanName = name.trim();
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanName) {
      setError('Please enter your full name.');
      return;
    }
    if (!cleanEmail.includes('@') || !cleanEmail.includes('.')) {
      setError('Please enter a valid email address.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Demo payment: always approved, nothing is charged or recorded.
      await new Promise((r) => setTimeout(r, 800));

      const guest = await api<{ id: string }>('/guests', {
        method: 'POST',
        body: { name: cleanName, email: cleanEmail },
      });
      const booking = await api<Created>('/bookings/apaleo', {
        method: 'POST',
        body: {
          guest_id: guest.id,
          room_id: 'room1',
          arrival: p.arrival,
          departure: p.departure,
          adults,
          rate_plan_id: p.rate_plan_id,
        },
      });
      await setToken(booking.guest_token);
      await setTrip({ bookingId: booking.id, guestId: booking.guest_id });
      router.replace('/trips');
    } catch (e: any) {
      setError(e.message ?? 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <GScreen>
      <TopBar onBack={() => router.back()} />
      <Text style={styles.title}>Almost there</Text>
      <Text style={styles.sub}>Check your stay, then tell us who is coming.</Text>

      <GCard style={{ padding: 0 }}>
        <Image source={roomPhoto(p.room_type)} style={styles.photo} resizeMode="cover" />
        <View style={{ padding: 16 }}>
          <Text style={styles.room}>{p.room_type}</Text>
          {p.rate_plan ? <Text style={styles.muted}>{p.rate_plan}</Text> : null}

          <View style={styles.divider} />
          <Row label="Arrive" value={prettyDate(p.arrival)} />
          <Row label="Depart" value={prettyDate(p.departure)} />
          <Row label="Guests" value={`${adults} adult${adults === 1 ? '' : 's'}`} />

          <View style={styles.divider} />
          <Row label={`Room · ${nights} night${nights === 1 ? '' : 's'}`} value={total} />
          <View style={styles.totalRow}>
            <Text style={styles.totalLabel}>Total</Text>
            <Text style={styles.totalValue}>{total}</Text>
          </View>
        </View>
      </GCard>

      <GCard>
        <Text style={styles.section}>Your details</Text>
        <GField
          label="Full name"
          value={name}
          onChangeText={setName}
          autoCapitalize="words"
          autoComplete="name"
        />
        <GField
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="email-address"
          autoComplete="email"
        />
      </GCard>

      <View style={styles.demo}>
        <Text style={styles.demoTitle}>Payment · DEMO</Text>
        <Text style={styles.muted}>
          No card is charged and nothing is recorded. Real payments are added later.
        </Text>
      </View>

      {error && <GBanner text={error} />}

      <View style={{ marginTop: 18 }}>
        <PrimaryButton
          label={busy ? 'Booking…' : `Confirm booking · ${total}`}
          onPress={confirm}
          disabled={busy}
        />
      </View>
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
  title: { color: light.ink, fontSize: 28, fontWeight: '800' },
  sub: { color: light.muted, fontSize: 15, marginTop: 4 },
  photo: { width: '100%', height: 150 },
  room: { color: light.ink, fontSize: 20, fontWeight: '800' },
  muted: { color: light.muted, fontSize: 14, marginTop: 4, lineHeight: 20 },
  divider: { height: 1, backgroundColor: light.line, marginVertical: 12 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  rowLabel: { color: light.muted, fontSize: 15 },
  rowValue: { color: light.ink, fontSize: 15, fontWeight: '600' },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 8,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: light.line,
  },
  totalLabel: { color: light.ink, fontSize: 17, fontWeight: '800' },
  totalValue: { color: light.ink, fontSize: 20, fontWeight: '800' },
  section: { color: light.ink, fontSize: 17, fontWeight: '800' },
  demo: {
    borderWidth: 1,
    borderColor: light.amber,
    borderStyle: 'dashed',
    borderRadius: 14,
    padding: 14,
    marginTop: 14,
    backgroundColor: '#FFF7EA',
  },
  demoTitle: { color: '#9A5B00', fontWeight: '800', letterSpacing: 0.5 },
});
