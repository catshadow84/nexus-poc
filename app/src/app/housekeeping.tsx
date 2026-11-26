import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { router, useFocusEffect, type Href } from 'expo-router';
import { api } from '@/lib/api';
import { brand } from '@/lib/brand';
import { getStaff, type StaffRole } from '@/lib/session';
import { Banner, Button, Card, Chip, Header, Screen, ago, layout, roomLabel, text } from '@/components/ui';

type CleanState = 'dirty' | 'cleaning' | 'clean' | 'inspected';
type Room = {
  room_id: string;
  occupied: boolean;
  clean_state: CleanState;
  updated_at: string | null;
  updated_by: string | null;
  open_issues: number;
};
type Data = { rooms: Room[]; summary: Record<CleanState, number> };

const LABEL: Record<CleanState, string> = {
  dirty: 'Dirty',
  cleaning: 'Cleaning',
  clean: 'Clean',
  inspected: 'Inspected',
};
const TONE: Record<CleanState, 'danger' | 'warn' | 'ok' | 'info'> = {
  dirty: 'danger',
  cleaning: 'warn',
  clean: 'ok',
  inspected: 'info',
};
const ORDER: Record<CleanState, number> = { dirty: 0, cleaning: 1, clean: 2, inspected: 3 };
const STATES: CleanState[] = ['dirty', 'cleaning', 'clean', 'inspected'];

export default function HousekeepingScreen() {
  const [data, setData] = useState<Data | null>(null);
  const [role, setRole] = useState<StaffRole | null>(null);
  const [filter, setFilter] = useState<CleanState | 'all'>('all');
  const [error, setError] = useState<string | null>(null);
  const [busyRoom, setBusyRoom] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api<Data>('/housekeeping/rooms'));
      setError(null);
    } catch (e: any) {
      if (e.status === 401) {
        router.replace('/signin');
        return;
      }
      setError(e.status === 403 ? 'Your role cannot see this screen.' : (e.message ?? 'Could not load rooms'));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      getStaff().then((s) => setRole(s?.role ?? null));
      load();
      const timer = setInterval(load, 15000);
      return () => clearInterval(timer);
    }, [load]),
  );

  async function changeState(roomId: string, state: CleanState) {
    setBusyRoom(roomId);
    setError(null);
    try {
      await api(`/housekeeping/rooms/${roomId}/status`, { method: 'POST', body: { state } });
      await load();
    } catch (e: any) {
      setError(e.message ?? 'Could not change the room');
    } finally {
      setBusyRoom(null);
    }
  }

  const supervisor = role === 'front_desk' || role === 'manager';
  const choices = supervisor ? STATES : (['cleaning', 'clean'] as CleanState[]);
  const rooms = (data?.rooms ?? [])
    .filter((r) => filter === 'all' || r.clean_state === filter)
    .sort((a, b) => ORDER[a.clean_state] - ORDER[b.clean_state] || a.room_id.localeCompare(b.room_id));

  return (
    <Screen>
      <Header
        title="Housekeeping"
        subtitle="Rooms update every 15 seconds."
        onBack={() => router.replace('/staff-home')}
      />

      {data && (
        <View style={layout.row}>
          <Chip label={`All ${data.rooms.length}`} selected={filter === 'all'} onPress={() => setFilter('all')} />
          {STATES.map((s) => (
            <Chip
              key={s}
              label={`${LABEL[s]} ${data.summary[s] ?? 0}`}
              tone={TONE[s]}
              selected={filter === s}
              onPress={() => setFilter(filter === s ? 'all' : s)}
            />
          ))}
        </View>
      )}

      {error && <Banner text={error} />}
      {!data && !error && <Text style={{ color: brand.muted, marginTop: 16 }}>Loading rooms…</Text>}
      {data && rooms.length === 0 && <Text style={{ color: brand.muted, marginTop: 16 }}>No rooms in this view.</Text>}

      {rooms.map((room) => (
        <Card key={room.room_id}>
          <View style={layout.rowSpread}>
            <Text style={text.strong}>{roomLabel(room.room_id)}</Text>
            <View style={layout.row}>
              {room.occupied && <Chip label="Occupied" tone="info" />}
              {room.open_issues > 0 && (
                <Chip label={`${room.open_issues} issue${room.open_issues > 1 ? 's' : ''}`} tone="danger" />
              )}
              <Chip label={LABEL[room.clean_state]} tone={TONE[room.clean_state]} selected />
            </View>
          </View>
          {room.updated_at && (
            <Text style={text.muted}>
              Updated {ago(room.updated_at)}
              {room.updated_by ? ` by ${room.updated_by}` : ''}
            </Text>
          )}
          <View style={[layout.row, layout.gap]}>
            {choices
              .filter((s) => s !== room.clean_state)
              .map((s) => (
                <Button
                  key={s}
                  small
                  kind={s === 'clean' || s === 'inspected' ? 'primary' : 'ghost'}
                  label={s === 'cleaning' ? 'Start cleaning' : `Mark ${LABEL[s].toLowerCase()}`}
                  disabled={busyRoom === room.room_id}
                  onPress={() => changeState(room.room_id, s)}
                />
              ))}
            <Button
              small
              kind="ghost"
              label="Report issue"
              onPress={() => router.push(`/maintenance?room_id=${room.room_id}` as Href)}
            />
          </View>
        </Card>
      ))}
    </Screen>
  );
}