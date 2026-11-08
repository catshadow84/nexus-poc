import { useCallback, useState } from 'react';
import { Text, View, TextInput, Pressable, ScrollView, StyleSheet, Alert } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { api } from '@/lib/api';

type Row = {
  booking_id: string;
  status: string;
  room_id: string;
  guest_name: string;
  guest_email: string;
  arrival: string | null;
  departure: string | null;
  reservation: string | null;
};
type Overview = { day: string; arrivals: Row[]; in_house: Row[]; departures: Row[] };

export default function StaffScreen() {
  const [day, setDay] = useState('');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async (d: string) => {
    setError(null);
    try {
      setOverview(await api<Overview>(`/staff/overview${d ? `?day=${d}` : ''}`));
    } catch (e: any) {
      setError(e.message ?? 'Could not load');
      if (e.status === 401 || e.status === 403) router.replace('/signin');
    }
  }, []);

  async function runSearch(q: string) {
    setError(null);
    try {
      setResults(await api<Row[]>(`/staff/search?q=${encodeURIComponent(q)}`));
    } catch (e: any) {
      setError(e.message ?? 'Search failed');
    }
  }

  useFocusEffect(
    useCallback(() => {
      loadOverview(day);
      if (results) runSearch(query);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [loadOverview]),
  );

  async function act(row: Row, action: 'checkin' | 'checkout' | 'cancel') {
    try {
      await api(`/bookings/${row.booking_id}/${action}`, { method: 'POST' });
      await loadOverview(day);
      if (results) await runSearch(query);
    } catch (e: any) {
      Alert.alert('Action failed', e.message ?? 'Something went wrong');
    }
  }

  function confirmCancel(row: Row) {
    Alert.alert('Cancel this reservation?', `${row.guest_name} (${row.arrival})`, [
      { text: 'Keep it', style: 'cancel' },
      { text: 'Cancel reservation', style: 'destructive', onPress: () => act(row, 'cancel') },
    ]);
  }

  function RowCard({ row }: { row: Row }) {
    return (
      <View style={styles.card}>
        <Text style={styles.name}>{row.guest_name}</Text>
        <Text style={styles.muted}>{row.guest_email}</Text>
        <Text style={styles.muted}>
          {row.arrival} → {row.departure} · {row.room_id} · {row.status}
        </Text>
        {row.reservation && <Text style={styles.muted}>Reservation {row.reservation}</Text>}
        <View style={styles.actions}>
          {row.status === 'RESERVED' && (
            <>
              <Pressable style={styles.btn} onPress={() => act(row, 'checkin')}>
                <Text style={styles.btnText}>Check in</Text>
              </Pressable>
              <Pressable style={styles.btnGhost} onPress={() => confirmCancel(row)}>
                <Text style={styles.btnGhostText}>Cancel</Text>
              </Pressable>
            </>
          )}
          {row.status === 'CHECKED_IN' && (
            <>
              <Pressable style={styles.btn} onPress={() => act(row, 'checkout')}>
                <Text style={styles.btnText}>Check out</Text>
              </Pressable>
              <Pressable
                style={styles.btnGhost}
                onPress={() =>
                  router.push({ pathname: '/services', params: { booking_id: row.booking_id } })
                }
              >
                <Text style={styles.btnGhostText}>Add service</Text>
              </Pressable>
            </>
          )}
        </View>
      </View>
    );
  }

  function Section({ title, rows }: { title: string; rows: Row[] }) {
    return (
      <View style={{ marginTop: 20 }}>
        <Text style={styles.section}>
          {title} ({rows.length})
        </Text>
        {rows.length === 0 && <Text style={styles.muted}>None</Text>}
        {rows.map((r) => (
          <RowCard key={`${title}-${r.booking_id}`} row={r} />
        ))}
      </View>
    );
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.inner}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.subtitle}>STAFF DESK</Text>

      <Text style={styles.label}>Find a reservation (name, email or reservation ID)</Text>
      <View style={styles.row}>
        <TextInput
          style={[styles.input, { flex: 1 }]}
          value={query}
          onChangeText={setQuery}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Pressable style={styles.btn} onPress={() => runSearch(query)}>
          <Text style={styles.btnText}>Find</Text>
        </Pressable>
      </View>

      {error && <Text style={styles.err}>{error}</Text>}

      {results ? (
        <View>
          <Pressable onPress={() => setResults(null)}>
            <Text style={styles.link}>Clear search</Text>
          </Pressable>
          <Section title="Results" rows={results} />
        </View>
      ) : (
        <View>
          <Text style={[styles.label, { marginTop: 16 }]}>Date (YYYY-MM-DD, empty = today)</Text>
          <View style={styles.row}>
            <TextInput
              style={[styles.input, { flex: 1 }]}
              value={day}
              onChangeText={setDay}
              autoCapitalize="none"
              keyboardType="numbers-and-punctuation"
            />
            <Pressable style={styles.btn} onPress={() => loadOverview(day)}>
              <Text style={styles.btnText}>Go</Text>
            </Pressable>
          </View>
          {overview && (
            <View>
              <Text style={styles.muted}>Showing {overview.day}</Text>
              <Section title="Arrivals" rows={overview.arrivals} />
              <Section title="In house" rows={overview.in_house} />
              <Section title="Departures" rows={overview.departures} />
            </View>
          )}
        </View>
      )}

      <Pressable style={styles.secondary} onPress={() => router.replace('/')}>
        <Text style={styles.secondaryText}>Back to rooms</Text>
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
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  input: { backgroundColor: '#141414', color: '#fff', borderRadius: 10, padding: 12 },
  section: { color: '#fff', fontSize: 16, fontWeight: '600', letterSpacing: 1, marginBottom: 6 },
  card: { backgroundColor: '#141414', borderRadius: 14, padding: 14, marginTop: 8 },
  name: { color: '#fff', fontSize: 16, fontWeight: '600' },
  muted: { color: '#888', marginTop: 3 },
  actions: { flexDirection: 'row', gap: 8, marginTop: 12 },
  btn: { backgroundColor: '#fff', borderRadius: 8, paddingVertical: 10, paddingHorizontal: 14 },
  btnText: { color: '#000', fontWeight: '600' },
  btnGhost: { borderWidth: 1, borderColor: '#333', borderRadius: 8, paddingVertical: 10, paddingHorizontal: 14 },
  btnGhostText: { color: '#fff' },
  err: { color: '#f87171', marginTop: 12 },
  link: { color: '#8a94a3', marginTop: 12, letterSpacing: 1 },
  secondary: { borderWidth: 1, borderColor: '#333', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 28 },
  secondaryText: { color: '#fff', letterSpacing: 1 },
});