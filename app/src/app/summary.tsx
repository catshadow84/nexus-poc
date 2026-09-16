import { useEffect, useState } from 'react';
import {
  Text, View, StyleSheet, ScrollView, Pressable, ActivityIndicator,
} from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';

const BACKEND = 'http://10.21.152.142:8000';

type Order = {
  id: string;
  item: string;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
};

type Summary = {
  booking_id: string;
  status: string;
  guest: { id: string; name: string; email: string };
  check_in: string | null;
  check_out: string | null;
  nights: number;
  room_charge_cents: number;
  orders: Order[];
  orders_total_cents: number;
  total_cents: number;
  carbon_kg: number;
  currency: string;
};

function money(cents: number, currency = 'USD') {
  return `${(cents / 100).toFixed(2)} ${currency}`;
}

function shortDate(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function SummaryScreen() {
  const params = useLocalSearchParams<{ booking_id: string }>();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.booking_id) return;
    fetch(`${BACKEND}/bookings/${params.booking_id}/summary`)
      .then((r) => r.json())
      .then(setSummary)
      .catch((e) => setError(String(e)));
  }, [params.booking_id]);

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.err}>Failed to load summary</Text>
        <Text style={styles.muted}>{error}</Text>
      </View>
    );
  }

  if (!summary) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#fff" />
      </View>
    );
  }

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.inner}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.subtitle}>Stay summary</Text>

      <View style={styles.card}>
        <Text style={styles.guest}>{summary.guest.name ?? 'Guest'}</Text>
        <Text style={styles.meta}>{summary.guest.email ?? ''}</Text>
        <View style={styles.divider} />
        <View style={styles.rowBetween}>
          <Text style={styles.label}>Check-in</Text>
          <Text style={styles.value}>{shortDate(summary.check_in)}</Text>
        </View>
        <View style={styles.rowBetween}>
          <Text style={styles.label}>Check-out</Text>
          <Text style={styles.value}>{shortDate(summary.check_out)}</Text>
        </View>
        <View style={styles.rowBetween}>
          <Text style={styles.label}>Nights</Text>
          <Text style={styles.value}>{summary.nights}</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Charges</Text>
        <View style={styles.rowBetween}>
          <Text style={styles.label}>Room · {summary.nights} night{summary.nights === 1 ? '' : 's'}</Text>
          <Text style={styles.value}>{money(summary.room_charge_cents, summary.currency)}</Text>
        </View>
        {summary.orders.map((o) => (
          <View key={o.id} style={styles.rowBetween}>
            <Text style={styles.label}>
              {o.quantity}× {o.item}
            </Text>
            <Text style={styles.value}>{money(o.line_total_cents, summary.currency)}</Text>
          </View>
        ))}
        <View style={styles.divider} />
        <View style={styles.rowBetween}>
          <Text style={styles.total}>Total</Text>
          <Text style={styles.total}>{money(summary.total_cents, summary.currency)}</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Sustainability</Text>
        <Text style={styles.muted}>
          Estimated carbon footprint for this stay: {summary.carbon_kg} kg CO₂e
        </Text>
      </View>

      <Pressable
        style={styles.btn}
        onPress={() => router.replace('/')}
      >
        <Text style={styles.btnText}>Done</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0a0a0a' },
  inner: { padding: 24, paddingTop: 72, paddingBottom: 40 },
  center: {
    flex: 1, backgroundColor: '#0a0a0a',
    alignItems: 'center', justifyContent: 'center',
  },
  brand: { color: '#fff', fontSize: 36, fontWeight: 'bold', letterSpacing: 8 },
  subtitle: { color: '#888', marginTop: 8, marginBottom: 24, letterSpacing: 2 },
  err: { color: '#f87171', marginBottom: 8, letterSpacing: 1 },
  muted: { color: '#888', fontSize: 13, lineHeight: 20 },

  card: {
    backgroundColor: '#141414',
    borderWidth: 1,
    borderColor: '#222',
    borderRadius: 14,
    padding: 18,
    marginBottom: 16,
  },
  guest: { color: '#fff', fontSize: 20, fontWeight: '600' },
  meta: { color: '#888', fontSize: 13, marginTop: 4 },
  divider: {
    height: 1, backgroundColor: '#222', marginVertical: 12,
  },
  sectionTitle: {
    color: '#fff', fontSize: 14, letterSpacing: 2,
    marginBottom: 12, fontWeight: '600',
  },
  rowBetween: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
  },
  label: { color: '#aaa', fontSize: 14 },
  value: { color: '#fff', fontSize: 14 },
  total: { color: '#fff', fontSize: 16, fontWeight: '700' },

  btn: {
    backgroundColor: '#fff',
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  btnText: { color: '#000', fontWeight: '700', letterSpacing: 1 },
});