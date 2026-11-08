import { useState } from 'react';
import {
  Text, View, TextInput, Pressable, ScrollView, StyleSheet, ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { api } from '@/lib/api';

type Offer = {
  rate_plan_id: string;
  room_type: string | null;
  rate_plan: string | null;
  total_amount: number;
  currency: string;
  guarantee: string | null;
  available_units: number | null;
  bookable: boolean;
};

const pad = (n: number) => String(n).padStart(2, '0');
const toIso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
function addDays(iso: string, n: number) {
  const [y, m, d] = iso.split('-').map(Number);
  return toIso(new Date(y, m - 1, d + n));
}
function validIso(s: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const [y, m, d] = s.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d;
}

function Stepper(props: { label: string; value: number; min: number; max: number; onChange: (n: number) => void }) {
  return (
    <View style={styles.stepRow}>
      <Text style={styles.label}>{props.label}</Text>
      <View style={styles.stepBox}>
        <Pressable style={styles.stepBtn} onPress={() => props.onChange(Math.max(props.min, props.value - 1))}>
          <Text style={styles.stepText}>−</Text>
        </Pressable>
        <Text style={styles.stepValue}>{props.value}</Text>
        <Pressable style={styles.stepBtn} onPress={() => props.onChange(Math.min(props.max, props.value + 1))}>
          <Text style={styles.stepText}>+</Text>
        </Pressable>
      </View>
    </View>
  );
}

export default function SearchScreen() {
  const [arrival, setArrival] = useState(addDays(toIso(new Date()), 30));
  const [nights, setNights] = useState(2);
  const [adults, setAdults] = useState(2);
  const [offers, setOffers] = useState<Offer[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const departure = validIso(arrival) ? addDays(arrival, nights) : '';

  async function search() {
    setError(null);
    setOffers(null);
    if (!validIso(arrival)) {
      setError('Use the date format YYYY-MM-DD, for example 2026-12-20.');
      return;
    }
    setLoading(true);
    try {
      const data = await api<Offer[]>(
        `/offers?arrival=${arrival}&departure=${departure}&adults=${adults}`,
      );
      setOffers(data);
    } catch (e: any) {
      setError(e.message ?? 'Search failed');
    } finally {
      setLoading(false);
    }
  }

  function select(o: Offer) {
    router.push({
      pathname: '/reserve',
      params: {
        arrival,
        departure,
        nights: String(nights),
        adults: String(adults),
        rate_plan_id: o.rate_plan_id,
        room_type: o.room_type ?? 'Room',
        rate_plan: o.rate_plan ?? '',
        total: String(o.total_amount),
        currency: o.currency,
      },
    });
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.inner}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.subtitle}>FIND A ROOM</Text>

      <Text style={styles.label}>Arrival (YYYY-MM-DD)</Text>
      <TextInput
        style={styles.input}
        value={arrival}
        onChangeText={setArrival}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="numbers-and-punctuation"
      />
      <Stepper label="Nights" value={nights} min={1} max={14} onChange={setNights} />
      <Stepper label="Adults" value={adults} min={1} max={6} onChange={setAdults} />
      {departure ? <Text style={styles.muted}>Departure {departure}</Text> : null}

      <Pressable style={[styles.btn, loading && { opacity: 0.5 }]} onPress={search} disabled={loading}>
        <Text style={styles.btnText}>{loading ? 'Searching…' : 'Search'}</Text>
      </Pressable>

      {loading && <ActivityIndicator style={{ marginTop: 16 }} />}
      {error && <Text style={styles.err}>{error}</Text>}
      {offers && offers.length === 0 && <Text style={styles.muted}>No rooms available for these dates.</Text>}

      {offers?.map((o) => (
        <View key={o.rate_plan_id} style={styles.card}>
          <Text style={styles.cardTitle}>{o.room_type ?? 'Room'}</Text>
          <Text style={styles.muted}>{o.rate_plan ?? ''}</Text>
          <Text style={styles.price}>
            {o.total_amount.toFixed(2)} {o.currency}
            <Text style={styles.muted}> for {nights} night{nights === 1 ? '' : 's'}</Text>
          </Text>
          {o.available_units != null && (
            <Text style={styles.muted}>{o.available_units} left</Text>
          )}
          {o.bookable ? (
            <Pressable style={styles.btn} onPress={() => select(o)}>
              <Text style={styles.btnText}>Select</Text>
            </Pressable>
          ) : (
            <Text style={styles.disabled}>Needs payment — not available in the demo</Text>
          )}
        </View>
      ))}

      <Pressable onPress={() => router.push('/signin')} style={{ marginTop: 32 }}>
        <Text style={styles.link}>Staff sign-in</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: '#0a0a0a' },
  inner: { padding: 24, paddingTop: 72, paddingBottom: 64 },
  brand: { color: '#fff', fontSize: 36, fontWeight: 'bold', letterSpacing: 8 },
  subtitle: { color: '#888', marginTop: 8, marginBottom: 24, letterSpacing: 2 },
  label: { color: '#666', fontSize: 12, letterSpacing: 1, marginBottom: 4 },
  input: { backgroundColor: '#141414', color: '#fff', borderRadius: 10, padding: 14, marginBottom: 12 },
  stepRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  stepBox: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  stepBtn: { backgroundColor: '#141414', borderRadius: 8, width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  stepText: { color: '#fff', fontSize: 20 },
  stepValue: { color: '#fff', fontSize: 18, minWidth: 24, textAlign: 'center' },
  btn: { backgroundColor: '#fff', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 16 },
  btnText: { color: '#000', fontWeight: '600', letterSpacing: 1 },
  muted: { color: '#888', marginTop: 4 },
  err: { color: '#f87171', marginTop: 16 },
  card: { backgroundColor: '#141414', borderRadius: 14, padding: 16, marginTop: 16 },
  cardTitle: { color: '#fff', fontSize: 18, fontWeight: '600' },
  price: { color: '#fff', fontSize: 20, marginTop: 8 },
  disabled: { color: '#666', marginTop: 16 },
  link: { color: '#8a94a3', textAlign: 'center', letterSpacing: 1 },
});