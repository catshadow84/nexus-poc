import { useState } from 'react';
import { Text, View, TextInput, Pressable, ScrollView, StyleSheet, Alert } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { api } from '@/lib/api';
import { setToken, setTrip } from '@/lib/session';

type Created = { id: string; guest_id: string; guest_token: string };

export default function ReserveScreen() {
  const p = useLocalSearchParams<{
    arrival: string; departure: string; nights: string; adults: string;
    rate_plan_id: string; room_type: string; rate_plan: string;
    total: string; currency: string;
  }>();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);

  async function confirm() {
    const cleanName = name.trim();
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanName || !cleanEmail.includes('@')) {
      Alert.alert('Details needed', 'Please enter your name and a valid email address.');
      return;
    }
    setBusy(true);
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
          adults: Number(p.adults),
          rate_plan_id: p.rate_plan_id,
        },
      });
      await setToken(booking.guest_token);
      await setTrip({ bookingId: booking.id, guestId: booking.guest_id });
      router.replace('/trips');
    } catch (e: any) {
      Alert.alert('Booking failed', e.message ?? 'Something went wrong');
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.inner}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.subtitle}>CONFIRM YOUR STAY</Text>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>{p.room_type}</Text>
        <Text style={styles.muted}>{p.rate_plan}</Text>
        <Text style={styles.muted}>
          {p.arrival} → {p.departure} · {p.nights} night{p.nights === '1' ? '' : 's'} · {p.adults} adult{p.adults === '1' ? '' : 's'}
        </Text>
        <Text style={styles.price}>{Number(p.total).toFixed(2)} {p.currency}</Text>
      </View>

      <Text style={styles.label}>Name</Text>
      <TextInput style={styles.input} value={name} onChangeText={setName} autoCapitalize="words" />
      <Text style={styles.label}>Email</Text>
      <TextInput
        style={styles.input}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
      />

      <View style={styles.demo}>
        <Text style={styles.demoTitle}>Payment · DEMO</Text>
        <Text style={styles.muted}>
          No card is charged and nothing is recorded. Real payments are added later.
        </Text>
      </View>

      <Pressable style={[styles.btn, busy && { opacity: 0.5 }]} onPress={confirm} disabled={busy}>
        <Text style={styles.btnText}>{busy ? 'Booking…' : 'Confirm & pay (demo)'}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: '#0a0a0a' },
  inner: { padding: 24, paddingTop: 72, paddingBottom: 64 },
  brand: { color: '#fff', fontSize: 36, fontWeight: 'bold', letterSpacing: 8 },
  subtitle: { color: '#888', marginTop: 8, marginBottom: 24, letterSpacing: 2 },
  card: { backgroundColor: '#141414', borderRadius: 14, padding: 16, marginBottom: 24 },
  cardTitle: { color: '#fff', fontSize: 18, fontWeight: '600' },
  price: { color: '#fff', fontSize: 22, marginTop: 12 },
  muted: { color: '#888', marginTop: 4 },
  label: { color: '#666', fontSize: 12, letterSpacing: 1, marginBottom: 4 },
  input: { backgroundColor: '#141414', color: '#fff', borderRadius: 10, padding: 14, marginBottom: 16 },
  demo: { borderWidth: 1, borderColor: '#333', borderStyle: 'dashed', borderRadius: 12, padding: 14, marginTop: 8 },
  demoTitle: { color: '#fbbf24', letterSpacing: 1, fontWeight: '600' },
  btn: { backgroundColor: '#fff', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 24 },
  btnText: { color: '#000', fontWeight: '600', letterSpacing: 1 },
});