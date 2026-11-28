import { useCallback, useState } from 'react';
import { Alert, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { api } from '@/lib/api';
import { brand } from '@/lib/brand';
import { addDays, nightsBetween, prettyDate } from '@/lib/dates';
import { Banner, Button, Card, Chip, Field, Header, Screen, layout, roomLabel, text } from '@/components/ui';

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
type Action = 'checkin' | 'checkout' | 'cancel';

const STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'neutral' }> = {
  RESERVED: { label: 'Reserved', tone: 'warn' },
  CHECKED_IN: { label: 'Checked in', tone: 'ok' },
  CHECKED_OUT: { label: 'Checked out', tone: 'neutral' },
  CANCELED: { label: 'Canceled', tone: 'danger' },
  NO_SHOW: { label: 'No-show', tone: 'danger' },
};

function RowCard({
  row,
  busy,
  onAct,
}: {
  row: Row;
  busy: boolean;
  onAct: (row: Row, action: Action) => void;
}) {
  const status = STATUS[row.status] ?? { label: row.status, tone: 'neutral' as const };
  const nights = row.arrival && row.departure ? nightsBetween(row.arrival, row.departure) : null;
  return (
    <Card>
      <View style={layout.rowSpread}>
        <Text style={[text.strong, { flex: 1 }]}>{row.guest_name}</Text>
        <Chip label={status.label} tone={status.tone} />
      </View>
      <Text style={text.muted}>{row.guest_email}</Text>
      <Text style={text.muted}>
        {roomLabel(row.room_id)}
        {row.arrival && row.departure
          ? ` · ${prettyDate(row.arrival)} → ${prettyDate(row.departure)}${nights != null ? ` · ${nights} night${nights === 1 ? '' : 's'}` : ''}`
          : ''}
      </Text>
      {row.reservation ? <Text style={text.muted}>Reservation {row.reservation}</Text> : null}

      {(row.status === 'RESERVED' || row.status === 'CHECKED_IN') && (
        <View style={[layout.row, layout.gap]}>
          {row.status === 'RESERVED' && (
            <>
              <Button small label="Check in" disabled={busy} onPress={() => onAct(row, 'checkin')} />
              <Button small kind="danger" label="Cancel" disabled={busy} onPress={() => onAct(row, 'cancel')} />
            </>
          )}
          {row.status === 'CHECKED_IN' && (
            <>
              <Button small label="Check out" disabled={busy} onPress={() => onAct(row, 'checkout')} />
              <Button
                small
                kind="ghost"
                label="Add service"
                onPress={() =>
                  router.push({ pathname: '/services', params: { booking_id: row.booking_id } })
                }
              />
            </>
          )}
        </View>
      )}
    </Card>
  );
}

function Section({
  title,
  rows,
  busyId,
  onAct,
}: {
  title: string;
  rows: Row[];
  busyId: string | null;
  onAct: (row: Row, action: Action) => void;
}) {
  return (
    <View style={{ marginTop: 22 }}>
      <View style={layout.rowSpread}>
        <Text style={text.strong}>{title}</Text>
        <Chip label={String(rows.length)} tone={rows.length ? 'info' : 'neutral'} />
      </View>
      {rows.length === 0 && <Text style={text.muted}>None</Text>}
      {rows.map((r) => (
        <RowCard key={`${title}-${r.booking_id}`} row={r} busy={busyId === r.booking_id} onAct={onAct} />
      ))}
    </View>
  );
}

export default function StaffScreen() {
  const [day, setDay] = useState('');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadOverview = useCallback(async (d: string) => {
    setError(null);
    try {
      setOverview(await api<Overview>(`/staff/overview${d ? `?day=${d}` : ''}`));
    } catch (e: any) {
      if (e.status === 401 || e.status === 403) {
        router.replace('/signin');
        return;
      }
      setError(e.message ?? 'Could not load the desk');
    }
  }, []);

  async function runSearch(q: string) {
    setError(null);
    try {
      setResults(await api<Row[]>(`/staff/search?q=${encodeURIComponent(q.trim())}`));
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

  async function perform(row: Row, action: Action) {
    setBusyId(row.booking_id);
    try {
      await api(`/bookings/${row.booking_id}/${action}`, { method: 'POST' });
      await loadOverview(day);
      if (results) await runSearch(query);
    } catch (e: any) {
      Alert.alert('Action failed', e.message ?? 'Something went wrong');
    } finally {
      setBusyId(null);
    }
  }

  function act(row: Row, action: Action) {
    if (action === 'checkin') {
      perform(row, action);
    } else if (action === 'checkout') {
      Alert.alert(
        'Check out this guest?',
        `${row.guest_name}, ${roomLabel(row.room_id)}. The room goes to eco mode, the door code stops working and the room is marked dirty.`,
        [
          { text: 'Not yet', style: 'cancel' },
          { text: 'Check out', onPress: () => perform(row, action) },
        ],
      );
    } else {
      Alert.alert('Cancel this reservation?', `${row.guest_name}${row.arrival ? ` (${prettyDate(row.arrival)})` : ''}`, [
        { text: 'Keep it', style: 'cancel' },
        { text: 'Cancel reservation', style: 'destructive', onPress: () => perform(row, action) },
      ]);
    }
  }

  function goToDay(next: string) {
    setDay(next);
    loadOverview(next);
  }

  const shownDay = overview?.day ?? '';

  return (
    <Screen>
      <Header
        title="Front desk"
        subtitle="Arrivals, departures and guests in the house."
        onBack={() => router.replace('/staff-home')}
      />

      <Card>
        <Field
          label="Find a reservation"
          placeholder="Name, email or reservation ID"
          value={query}
          onChangeText={setQuery}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="search"
          onSubmitEditing={() => query.trim() && runSearch(query)}
        />
        <View style={[layout.row, layout.gap]}>
          <Button small label="Find" disabled={query.trim().length < 2} onPress={() => runSearch(query)} />
          {results && (
            <Button
              small
              kind="ghost"
              label="Clear search"
              onPress={() => {
                setResults(null);
                setQuery('');
                setError(null);
              }}
            />
          )}
        </View>
      </Card>

      {error && <Banner text={error} />}

      {results ? (
        <>
          <Section title="Results" rows={results} busyId={busyId} onAct={act} />
          {results.length === 0 && <Banner tone="info" text="No reservation matches that search." />}
        </>
      ) : (
        <>
          <Card>
            <View style={layout.rowSpread}>
              <Button
                small
                kind="ghost"
                label="‹"
                disabled={!shownDay}
                onPress={() => goToDay(addDays(shownDay, -1))}
              />
              <View style={{ flex: 1, alignItems: 'center' }}>
                <Text style={text.strong}>{shownDay ? prettyDate(shownDay) : 'Today'}</Text>
                {!day && shownDay ? <Text style={{ color: brand.muted, fontSize: 12 }}>Today</Text> : null}
              </View>
              <Button
                small
                kind="ghost"
                label="›"
                disabled={!shownDay}
                onPress={() => goToDay(addDays(shownDay, 1))}
              />
            </View>
            <View style={[layout.row, layout.gap]}>
              {day ? <Button small kind="ghost" label="Back to today" onPress={() => goToDay('')} /> : null}
              <Button small kind="ghost" label="Refresh" onPress={() => loadOverview(day)} />
            </View>
          </Card>

          {!overview && !error && <Text style={{ color: brand.muted, marginTop: 16 }}>Loading…</Text>}
          {overview && (
            <>
              <Section title="Arrivals" rows={overview.arrivals} busyId={busyId} onAct={act} />
              <Section title="In house" rows={overview.in_house} busyId={busyId} onAct={act} />
              <Section title="Departures" rows={overview.departures} busyId={busyId} onAct={act} />
            </>
          )}
        </>
      )}
    </Screen>
  );
}
