import { useEffect, useState } from 'react';
import { Text, View, Pressable, ScrollView, StyleSheet, Alert } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { api } from '@/lib/api';
import { getTrip } from '@/lib/session';

type MenuItem = { item: string; price_cents: number };

export default function ServicesScreen() {
    const params = useLocalSearchParams<{ booking_id?: string }>();
  const [items, setItems] = useState<MenuItem[]>([]);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api<{ items: MenuItem[] }>('/menu')
      .then((d) => setItems(d.items))
      .catch((e) => Alert.alert('Could not load the menu', e.message));
  }, []);

  const q = (item: string) => qty[item] ?? 1;
  const change = (item: string, delta: number) =>
    setQty((s) => ({ ...s, [item]: Math.min(10, Math.max(1, (s[item] ?? 1) + delta)) }));

  async function order(item: string) {
  const bookingId = params.booking_id ?? (await getTrip())?.bookingId;
  if (!bookingId) {
      Alert.alert('Guests only', 'Sign in as a guest with an active stay to order.');
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await api(`/bookings/${bookingId}/orders`, {
        method: 'POST',
        body: { item, quantity: q(item) },
      });
      setMessage(`Ordered ${q(item)} × ${item}. It is on your bill.`);
    } catch (e: any) {
      Alert.alert('Could not order', e.message ?? 'Something went wrong');
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.inner}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.subtitle}>ROOM SERVICE</Text>

      {items.map((m) => (
        <View key={m.item} style={styles.card}>
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{m.item}</Text>
            <Text style={styles.muted}>${(m.price_cents / 100).toFixed(2)}</Text>
          </View>
          <View style={styles.stepBox}>
            <Pressable style={styles.stepBtn} onPress={() => change(m.item, -1)}>
              <Text style={styles.stepText}>−</Text>
            </Pressable>
            <Text style={styles.stepValue}>{q(m.item)}</Text>
            <Pressable style={styles.stepBtn} onPress={() => change(m.item, 1)}>
              <Text style={styles.stepText}>+</Text>
            </Pressable>
          </View>
          <Pressable style={[styles.btn, busy && { opacity: 0.5 }]} onPress={() => order(m.item)} disabled={busy}>
            <Text style={styles.btnText}>Order</Text>
          </Pressable>
        </View>
      ))}

      {message && <Text style={styles.ok}>{message}</Text>}

      <Pressable style={styles.secondary} onPress={() => router.back()}>
        <Text style={styles.secondaryText}>Back</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: '#0a0a0a' },
  inner: { padding: 24, paddingTop: 72, paddingBottom: 64 },
  brand: { color: '#fff', fontSize: 36, fontWeight: 'bold', letterSpacing: 8 },
  subtitle: { color: '#888', marginTop: 8, marginBottom: 24, letterSpacing: 2 },
  card: { backgroundColor: '#141414', borderRadius: 14, padding: 14, marginBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 10 },
  name: { color: '#fff', fontSize: 16, textTransform: 'capitalize' },
  muted: { color: '#888', marginTop: 2 },
  stepBox: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  stepBtn: { backgroundColor: '#222', borderRadius: 8, width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  stepText: { color: '#fff', fontSize: 18 },
  stepValue: { color: '#fff', minWidth: 18, textAlign: 'center' },
  btn: { backgroundColor: '#fff', borderRadius: 8, paddingVertical: 10, paddingHorizontal: 14 },
  btnText: { color: '#000', fontWeight: '600' },
  ok: { color: '#4ade80', marginTop: 12 },
  secondary: { borderWidth: 1, borderColor: '#333', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 20 },
  secondaryText: { color: '#fff', letterSpacing: 1 },
});