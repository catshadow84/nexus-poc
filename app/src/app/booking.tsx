import { useState, useEffect } from 'react';
import { useLocalSearchParams } from 'expo-router';
import {
  Text, View, TextInput, Pressable, StyleSheet, ScrollView, Alert,
} from 'react-native';
import { API_URL } from '@/config';



function buildPreferences(name: string) {
  const hash = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const profiles = [
    {
      light: { power: 'on', brightness: 60, color: 'warm' },
      thermostat: { target_c: 21, mode: 'cool' },
      curtain: { open_pct: 30 },
    },
    {
      light: { power: 'on', brightness: 100, color: 'cool' },
      thermostat: { target_c: 24, mode: 'cool' },
      curtain: { open_pct: 0 },
    },
    {
      light: { power: 'off', brightness: 0, color: 'neutral' },
      thermostat: { target_c: 19, mode: 'heat' },
      curtain: { open_pct: 100 },
    },
  ];
  return profiles[hash % profiles.length];
}

export default function BookingScreen() {
  const params = useLocalSearchParams<{ room_id?: string }>();
  const roomId = params.room_id ?? 'room1';
  const [returning, setReturning] = useState<null | { name: string; stayCount: number }>(null);
  const [name, setName] = useState('Sarah Khoury');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
  if (!email || !email.includes('@')) {
    setReturning(null);
    return;
  }
  const t = setTimeout(() => {
    fetch(`${API_URL}/guests/lookup?email=${encodeURIComponent(email)}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.found) {
          setReturning({
            name: data.guest.name,
            stayCount: data.stay_count,
          });
          // pre-fill the name if it's still the default
          if (name === 'Sarah Khoury' || !name.trim()) {
            setName(data.guest.name);
          }
        } else {
          setReturning(null);
        }
      })
      .catch(() => setReturning(null));
  }, 400);
  return () => clearTimeout(t);
}, [email]);

  async function runScenario() {
    setBusy(true);
    setResult(null);
    try {
      // 1. create guest
      const guestRes = await fetch(`${API_URL}/guests`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name,
    email,
    preferences: returning ? {} : buildPreferences(name),
  }),
});
      if (!guestRes.ok) throw new Error(`guest: ${await guestRes.text()}`);
      const guest = await guestRes.json();

      // 2. create booking
      const bookingRes = await fetch(`${API_URL}/bookings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guest_id: guest.id, room_id: roomId }),
      });
      if (!bookingRes.ok) throw new Error(`booking: ${await bookingRes.text()}`);
      const booking = await bookingRes.json();
      
      // pre-step: if a booking is already checked in, check it out so the room is free
try {
  const activeRes = await fetch(`${API_URL}/bookings/active?room_id=${roomId}`);
  if (activeRes.ok) {
    const active = await activeRes.json();
    if (active && active.id) {
      await fetch(`${API_URL}/bookings/${active.id}/checkout`, {
        method: 'POST',
      });
    }
  }
} catch {
  // ignore — if it fails, the checkin below will report the real error
}
      // 3. check in
      const ciRes = await fetch(
        `${API_URL}/bookings/${booking.id}/checkin`,
        { method: 'POST' }
      );
      if (!ciRes.ok) throw new Error(`checkin: ${await ciRes.text()}`);
      const ci = await ciRes.json();

      setResult(`Checked in. Applied: ${ci.applied_devices.join(', ')}`);
    } catch (e: any) {
      Alert.alert('Failed', e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.inner}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.subtitle}>
  {returning
    ? `Welcome back, ${returning.name.split(' ')[0]}. ${returning.stayCount} previous stay${returning.stayCount === 1 ? '' : 's'}.`
    : 'New stay'}
</Text>

      <Text style={styles.label}>Name</Text>
      <TextInput
        style={styles.input}
        value={name}
        onChangeText={setName}
        autoCapitalize="words"
      />

      <Text style={styles.label}>Email</Text>
      <TextInput
        style={styles.input}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        keyboardType="email-address"
      />

      <Pressable
        style={[styles.btn, busy && { opacity: 0.5 }]}
        onPress={runScenario}
        disabled={busy}
      >
        <Text style={styles.btnText}>
          {busy ? 'Working…' : 'Book & Check In'}
        </Text>
      </Pressable>

      {result && <Text style={styles.result}>{result}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  subtitleReturning: {
  color: '#4ade80',
  marginTop: 8,
  marginBottom: 32,
  letterSpacing: 1,
  fontSize: 13,
},
  scroll: { flex: 1, backgroundColor: '#0a0a0a' },
  inner: { padding: 24, paddingTop: 72 },
  brand: { color: '#fff', fontSize: 36, fontWeight: 'bold', letterSpacing: 8 },
  subtitle: { color: '#888', marginTop: 8, marginBottom: 32, letterSpacing: 2 },
  label: { color: '#666', fontSize: 12, letterSpacing: 1, marginBottom: 4 },
  input: {
    backgroundColor: '#141414', color: '#fff',
    paddingVertical: 12, paddingHorizontal: 14,
    borderRadius: 10, marginBottom: 20,
    borderWidth: 1, borderColor: '#222',
  },
  btn: {
    backgroundColor: '#fff', paddingVertical: 14,
    borderRadius: 10, alignItems: 'center', marginTop: 8,
  },
  btnText: { color: '#000', fontWeight: '600', letterSpacing: 1 },
  result: { color: '#4ade80', marginTop: 24, letterSpacing: 1 },
});