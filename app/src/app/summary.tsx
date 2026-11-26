import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { api } from '@/lib/api';
import { light } from '@/lib/brand';
import {
  GBanner,
  GCard,
  GScreen,
  PrimaryButton,
  TopBar,
} from '@/components/guest-ui';

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
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function SummaryScreen() {
  const params = useLocalSearchParams<{ booking_id: string }>();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.booking_id) return;
    api<Summary>(`/bookings/${params.booking_id}/summary`)
      .then(setSummary)
      .catch((e) => setError(e?.message ?? String(e)));
  }, [params.booking_id]);

  return (
    <GScreen>
      <TopBar />
      <Text style={styles.title}>Stay summary</Text>

      {error && <GBanner text={`Could not load your summary. ${error}`} />}
      {!summary && !error && <ActivityIndicator style={{ marginTop: 32 }} color={light.navy} />}

      {summary && (
        <>
          <GCard>
            <Text style={styles.guest}>{summary.guest.name ?? 'Guest'}</Text>
            <Text style={styles.muted}>{summary.guest.email ?? ''}</Text>
            <View style={styles.divider} />
            <Row label="Check-in" value={shortDate(summary.check_in)} />
            <Row label="Check-out" value={shortDate(summary.check_out)} />
            <Row label="Nights" value={String(summary.nights)} />
          </GCard>

          <GCard>
            <Text style={styles.section}>Charges</Text>
            <Row
              label={`Room · ${summary.nights} night${summary.nights === 1 ? '' : 's'}`}
              value={money(summary.room_charge_cents, summary.currency)}
            />
            {summary.orders.map((o) => (
              <Row
                key={o.id}
                label={`${o.quantity}× ${o.item}`}
                value={money(o.line_total_cents, summary.currency)}
              />
            ))}
            <View style={styles.totalRow}>
              <Text style={styles.totalLabel}>Total</Text>
              <Text style={styles.totalValue}>{money(summary.total_cents, summary.currency)}</Text>
            </View>
          </GCard>

          <GCard>
            <Text style={styles.section}>Sustainability</Text>
            <Text style={styles.muted}>
              Estimated carbon footprint for this stay: {summary.carbon_kg} kg CO₂e
            </Text>
          </GCard>

          <View style={{ marginTop: 18 }}>
            <PrimaryButton label="Done" onPress={() => router.replace('/')} />
          </View>
        </>
      )}
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
  guest: { color: light.ink, fontSize: 20, fontWeight: '800' },
  muted: { color: light.muted, fontSize: 14, lineHeight: 20, marginTop: 4 },
  section: { color: light.ink, fontSize: 17, fontWeight: '800', marginBottom: 8 },
  divider: { height: 1, backgroundColor: light.line, marginVertical: 12 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5, gap: 12 },
  rowLabel: { color: light.muted, fontSize: 15, flexShrink: 1 },
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
});
