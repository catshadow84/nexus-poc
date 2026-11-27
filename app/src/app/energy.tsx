import { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { api } from '@/lib/api';
import { brand } from '@/lib/brand';
import { Banner, Button, Card, Chip, Header, Screen, layout, roomLabel, text } from '@/components/ui';

type RoomRow = {
  room_id: string;
  checkouts: number;
  vacant_hours: number;
  kwh_saved: number;
  money_saved: number;
  co2_kg_saved: number;
  live_mode: string | null;
  live_kw: number | null;
};

type Report = {
  currency: string;
  assumptions: {
    occupied_kw: number;
    eco_kw: number;
    price_per_kwh: number;
    kg_co2_per_kwh: number;
    cap_hours: number;
  };
  totals: {
    checkouts: number;
    vacant_hours: number;
    kwh_saved: number;
    money_saved: number;
    co2_kg_saved: number;
  };
  rooms: RoomRow[];
};

function fixed(n: number, digits = 1) {
  return n.toFixed(digits);
}

export default function EnergyScreen() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setReport(await api<Report>('/energy'));
      setError(null);
    } catch (e: any) {
      if (e.status === 401) {
        router.replace('/signin');
        return;
      }
      setError(
        e.status === 403
          ? 'Only managers can see the energy report.'
          : (e.message ?? 'Could not load the energy report'),
      );
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const a = report?.assumptions;
  const rooms = (report?.rooms ?? []).filter((r) => r.checkouts > 0 || r.live_mode);

  return (
    <Screen>
      <Header
        title="Energy savings"
        subtitle="Air conditioning set to eco after check-out."
        onBack={() => router.replace('/staff-home')}
      />

      {error && <Banner text={error} />}
      {!report && !error && <Text style={{ color: brand.muted, marginTop: 16 }}>Loading…</Text>}

      {report && (
        <>
          <Card>
            <Text style={styles.big}>
              {fixed(report.totals.money_saved, 2)} {report.currency}
            </Text>
            <Text style={text.muted}>estimated saved so far</Text>
            <View style={styles.stats}>
              <Stat value={fixed(report.totals.kwh_saved)} label="kWh saved" />
              <Stat value={fixed(report.totals.co2_kg_saved)} label="kg CO₂ avoided" />
              <Stat value={String(report.totals.checkouts)} label="check-outs" />
            </View>
          </Card>

          {rooms.length === 0 && (
            <Banner tone="info" text="No stays have ended yet. Check a guest out and the saving appears here." />
          )}

          {rooms.map((r) => (
            <Card key={r.room_id}>
              <View style={layout.rowSpread}>
                <Text style={[text.strong, { flex: 1 }]}>{roomLabel(r.room_id)}</Text>
                {r.live_mode ? (
                  <Chip
                    label={`AC ${r.live_mode}${r.live_kw != null ? ` · ${fixed(r.live_kw, 1)} kW` : ''}`}
                    tone={r.live_mode === 'eco' || r.live_mode === 'off' ? 'ok' : 'info'}
                  />
                ) : null}
              </View>
              <Text style={text.muted}>
                {r.checkouts} check-out{r.checkouts === 1 ? '' : 's'} · {fixed(r.vacant_hours)} h empty
              </Text>
              <Text style={text.muted}>
                {fixed(r.kwh_saved)} kWh · {fixed(r.money_saved, 2)} {report.currency} ·{' '}
                {fixed(r.co2_kg_saved)} kg CO₂
              </Text>
            </Card>
          ))}

          {a && (
            <Card>
              <Text style={text.strong}>How this is estimated</Text>
              <Text style={text.muted}>
                After each check-out the air conditioning runs in eco mode ({fixed(a.eco_kw)} kW) instead of its normal{' '}
                {fixed(a.occupied_kw)} kW, until the next guest arrives. Energy saved = empty hours ×{' '}
                {fixed(a.occupied_kw - a.eco_kw)} kW, priced at {fixed(a.price_per_kwh, 2)} {report.currency} per kWh and{' '}
                {fixed(a.kg_co2_per_kwh)} kg CO₂ per kWh. One empty stretch counts for at most {a.cap_hours} hours.
                These are estimates, not meter readings.
              </Text>
            </Card>
          )}
        </>
      )}

      <View style={layout.gap}>
        <Button label="Refresh" kind="ghost" onPress={load} />
      </View>
    </Screen>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  big: { color: brand.amber, fontSize: 34, fontWeight: '800' },
  stats: { flexDirection: 'row', gap: 12, marginTop: 16 },
  statValue: { color: brand.text, fontSize: 20, fontWeight: '700' },
  statLabel: { color: brand.muted, fontSize: 12, marginTop: 2 },
});
