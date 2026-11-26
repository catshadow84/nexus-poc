import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import Slider from '@react-native-community/slider';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { WS_URL } from '@/config';
import { api } from '@/lib/api';
import { brand } from '@/lib/brand';
import { clearToken, getStaff, getToken, getTrip } from '@/lib/session';
import {
  Banner,
  Button,
  Card,
  Chip,
  Header,
  Screen,
  layout,
  roomLabel,
  text,
} from '@/components/ui';

type DeviceState = {
  desired?: Record<string, any> | null;
  reported?: Record<string, any> | null;
  last_command_id?: string;
  last_updated?: string;
};

type RoomState = {
  room_id: string;
  devices: Record<string, DeviceState>;
};

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/** A labelled slider that sends its value when the finger is lifted. */
function Tune({
  label,
  value,
  min,
  max,
  step,
  onDone,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onDone: (v: number) => void;
}) {
  return (
    <View style={{ marginTop: 14 }}>
      <Text style={styles.sliderLabel}>{label}</Text>
      <Slider
        style={styles.slider}
        minimumValue={min}
        maximumValue={max}
        step={step}
        value={value}
        minimumTrackTintColor={brand.amber}
        maximumTrackTintColor={brand.border}
        thumbTintColor={brand.amber}
        onSlidingComplete={onDone}
      />
    </View>
  );
}

export default function HomeScreen() {
  const { controls } = useLocalSearchParams<{ controls?: string }>();
  const [isGuest, setIsGuest] = useState(false);
  const [guestName, setGuestName] = useState<string | null>(null);
  const [state, setState] = useState<RoomState | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const [bookingId, setBookingId] = useState<string | null>(null);
  const [roomId, setRoomId] = useState<'room1' | 'room2'>('room1');
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setConnected(false);
    setState(null);
    setGuestName(null);
    setBookingId(null);

    api<RoomState>(`/rooms/${roomId}/state`)
      .then((s) => {
        if (!cancelled) setState(s);
      })
      .catch((e) => {
        console.warn('initial fetch failed', e.message);
        if (e.status === 401) router.replace('/search');
      });

    const ws = new WebSocket(`${WS_URL}?room_id=${roomId}`);
    wsRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      getToken().then((t) => ws.send(JSON.stringify({ type: 'auth', token: t ?? '' })));
    };
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'state') setState(msg.data);
      } catch (err) {
        console.warn('bad ws message', err);
      }
    };

    (async () => {
      const token = await getToken();
      if (!token) {
        router.replace('/search');
        return;
      }
      const staffSession = await getStaff();
      if (staffSession && !controls) {
        router.replace('/staff-home');
        return;
      }
      const trip = await getTrip();
      try {
        if (trip) {
          // a guest: their own booking only, and only once checked in
          setIsGuest(true);
          const b = await api(`/bookings/${trip.bookingId}`);
          if (cancelled) return;
          if (b.status !== 'CHECKED_IN') {
            router.replace('/trips');
            return;
          }
          setRoomId(b.room_id);
          setBookingId(b.id);
          const g = await api(`/guests/${b.guest_id}`);
          if (!cancelled) setGuestName(g.name);
        } else {
          // staff: look up whoever is in this room
          setIsGuest(false);
          const b = await api(`/bookings/active?room_id=${roomId}`);
          if (b && b.id && !cancelled) {
            setBookingId(b.id);
            const g = await api(`/guests/${b.guest_id}`);
            if (!cancelled) setGuestName(g.name);
          }
        }
      } catch (e: any) {
        if (e?.status === 401) router.replace('/search');
      }
    })();

    return () => {
      cancelled = true;
      ws.close();
    };
  }, [roomId]);

  // When the screen comes back into view (for example after the summary),
  // a guest whose stay is over goes back to "My trip".
  useFocusEffect(
    useCallback(() => {
      let live = true;
      (async () => {
        const trip = await getTrip();
        if (!trip) return;
        try {
          const b = await api(`/bookings/${trip.bookingId}`);
          if (live && b.status !== 'CHECKED_IN') router.replace('/trips');
        } catch {
          // a 401 is handled by the main effect
        }
      })();
      return () => {
        live = false;
      };
    }, []),
  );

  async function signOut() {
    await clearToken();
    router.replace('/search');
  }

  async function sendCommand(device: string, value: Record<string, any>) {
    try {
      await api(`/rooms/${roomId}/device/${device}/command`, { method: 'POST', body: value });
      setNotice(null);
    } catch (e: any) {
      setNotice(e.message ?? 'The room did not accept that. Is the server running?');
    }
  }

  async function runScene(name: string) {
    try {
      await api(`/rooms/${roomId}/scenes/${name}`, { method: 'POST' });
      setNotice(null);
    } catch (e: any) {
      setNotice(e.message ?? 'The scene did not run. Is the server running?');
    }
  }

  function askCheckOut() {
    if (!bookingId) return;
    Alert.alert('Check out now?', 'This ends your stay and takes you to your receipt.', [
      { text: 'Stay', style: 'cancel' },
      { text: 'Check out', style: 'destructive', onPress: doCheckOut },
    ]);
  }

  async function doCheckOut() {
    if (!bookingId) return;
    try {
      await api(`/bookings/${bookingId}/checkout`, { method: 'POST' });
      router.push(`/summary?booking_id=${bookingId}`);
    } catch (e: any) {
      setNotice(e.message ?? 'Check-out failed. Is the server running?');
    }
  }

  if (!state || !state.devices) {
    return (
      <Screen>
        <Header title="Connecting…" subtitle="Reaching your room" />
      </Screen>
    );
  }

  const lamp = state.devices.light?.reported ?? {};
  const ac = state.devices.central_ac?.reported ?? {};
  const bose = state.devices.bose?.reported ?? {};
  const door = state.devices.door?.reported ?? {};
  const curtain = state.devices.curtain?.reported ?? {};

  const lampOn = lamp.power === 'on';
  const boseOn = bose.power === 'on';
  const unlocked = door.locked === false;
  const first = guestName ? guestName.split(' ')[0] : null;

  return (
    <Screen>
      <Header
        title={isGuest ? (first ? `Welcome, ${first}` : 'Your room') : 'Room controls'}
        subtitle={roomLabel(roomId)}
        onBack={
          isGuest
            ? undefined
            : async () => {
                router.replace((await getStaff()) ? '/staff-home' : '/staff');
              }
        }
      />

      <View style={layout.row}>
        <Chip label={connected ? 'Live' : 'Offline'} tone={connected ? 'ok' : 'danger'} selected />
        {!isGuest &&
          (['room1', 'room2'] as const).map((r) => (
            <Chip
              key={r}
              label={roomLabel(r)}
              tone="info"
              selected={roomId === r}
              onPress={() => setRoomId(r)}
            />
          ))}
        {!isGuest && guestName && <Chip label={`Guest: ${guestName}`} />}
      </View>

      {notice && <Banner text={notice} />}

      {/* ---- DOOR ---- */}
      <Card>
        <View style={layout.rowSpread}>
          <Text style={text.strong}>Door</Text>
          <Chip label={unlocked ? 'Unlocked' : 'Locked'} tone={unlocked ? 'warn' : 'ok'} selected />
        </View>
        <Text style={text.muted}>
          {unlocked ? 'The door locks again by itself.' : 'Tap to open your door.'}
        </Text>
        <View style={layout.gap}>
          <Button
            label="Unlock door"
            disabled={unlocked}
            onPress={() => sendCommand('door', { locked: false })}
          />
        </View>
      </Card>

      {/* ---- SCENES ---- */}
      <View style={styles.tiles}>
        <Pressable style={styles.tile} onPress={() => runScene('good_morning')} accessibilityRole="button">
          <Text style={styles.tileIcon}>☀︎</Text>
          <Text style={styles.tileText}>Good morning</Text>
        </Pressable>
        <Pressable style={styles.tile} onPress={() => runScene('focus')} accessibilityRole="button">
          <Text style={styles.tileIcon}>◆</Text>
          <Text style={styles.tileText}>Focus</Text>
        </Pressable>
        <Pressable style={styles.tile} onPress={() => runScene('goodnight')} accessibilityRole="button">
          <Text style={styles.tileIcon}>☾</Text>
          <Text style={styles.tileText}>Goodnight</Text>
        </Pressable>
      </View>

      {/* ---- SHORTCUTS ---- */}
      <View style={styles.tiles}>
        <Pressable
          style={styles.tile}
          onPress={() => router.push(`/nora?room_id=${roomId}`)}
          accessibilityRole="button"
        >
          <Text style={styles.tileIcon}>◉</Text>
          <Text style={styles.tileText}>Ask NORA</Text>
        </Pressable>
        {isGuest && (
          <>
            <Pressable style={styles.tile} onPress={() => router.push('/services')} accessibilityRole="button">
              <Text style={styles.tileIcon}>☕︎</Text>
              <Text style={styles.tileText}>Room service</Text>
            </Pressable>
            <Pressable
              style={styles.tile}
              onPress={() => router.push(bookingId ? `/summary?booking_id=${bookingId}` : '/trips')}
              accessibilityRole="button"
            >
              <Text style={styles.tileIcon}>≡</Text>
              <Text style={styles.tileText}>My bill</Text>
            </Pressable>
          </>
        )}
      </View>

      {/* ---- LIGHT ---- */}
      <Card>
        <View style={layout.rowSpread}>
          <Text style={text.strong}>Light</Text>
          <Chip
            label={lampOn ? `On · ${lamp.brightness ?? 0}%` : 'Off'}
            tone={lampOn ? 'warn' : 'neutral'}
            selected={lampOn}
          />
        </View>
        <View style={layout.gap}>
          <Button
            label={lampOn ? 'Turn off' : 'Turn on'}
            kind={lampOn ? 'ghost' : 'primary'}
            onPress={() =>
              sendCommand('light', {
                power: lampOn ? 'off' : 'on',
                brightness: lamp.brightness || 80,
                color: 'warm',
              })
            }
          />
        </View>
        <Tune
          label="Brightness"
          min={0}
          max={100}
          step={5}
          value={lamp.brightness ?? 0}
          onDone={(v) =>
            sendCommand('light', {
              power: 'on',
              brightness: Math.round(v),
              color: lamp.color || 'warm',
            })
          }
        />
        <View style={[layout.row, layout.gap]}>
          {(['warm', 'neutral', 'cool'] as const).map((c) => (
            <Chip
              key={c}
              label={c}
              tone={lamp.color === c ? 'warn' : 'neutral'}
              selected={lamp.color === c}
              onPress={() =>
                sendCommand('light', {
                  power: lamp.power || 'on',
                  brightness: lamp.brightness || 80,
                  color: c,
                })
              }
            />
          ))}
        </View>
      </Card>

      {/* ---- AIR CONDITIONING ---- */}
      <Card>
        <View style={layout.rowSpread}>
          <Text style={text.strong}>Air conditioning</Text>
          <Chip
            label={cap(ac.mode ?? 'cool')}
            tone={ac.mode === 'eco' ? 'ok' : ac.mode === 'off' ? 'neutral' : 'info'}
            selected={ac.mode !== 'off'}
          />
        </View>
        <Text style={styles.big}>{ac.current_c ?? '—'}°C</Text>
        <Text style={text.muted}>
          Target {ac.target_c ?? '—'}°C
          {ac.power_kw != null ? ` · using ${ac.power_kw} kW` : ''}
        </Text>
        <View style={[layout.row, layout.gap]}>
          {(['cool', 'heat', 'eco', 'off'] as const).map((m) => (
            <Chip
              key={m}
              label={cap(m)}
              tone={m === 'eco' ? 'ok' : 'info'}
              selected={ac.mode === m}
              onPress={() =>
                sendCommand('central_ac', {
                  target_c: m === 'eco' ? 26 : (ac.target_c ?? 22),
                  mode: m,
                })
              }
            />
          ))}
        </View>
        {ac.mode === 'eco' && (
          <Text style={text.muted}>Eco saves energy by keeping the room at 26°C.</Text>
        )}
        <Tune
          label="Target temperature"
          min={16}
          max={30}
          step={0.5}
          value={ac.target_c ?? 22}
          onDone={(v) =>
            sendCommand('central_ac', {
              target_c: Number(v.toFixed(1)),
              mode: ac.mode && ac.mode !== 'off' ? ac.mode : 'cool',
            })
          }
        />
      </Card>

      {/* ---- MUSIC ---- */}
      <Card>
        <View style={layout.rowSpread}>
          <Text style={text.strong}>Bose speaker</Text>
          <Chip
            label={boseOn ? (bose.playing ? 'Playing' : 'Paused') : 'Off'}
            tone={boseOn ? 'warn' : 'neutral'}
            selected={boseOn}
          />
        </View>
        <View style={layout.gap}>
          <Button
            label={boseOn ? 'Turn off' : 'Turn on'}
            kind={boseOn ? 'ghost' : 'primary'}
            onPress={() =>
              sendCommand('bose', {
                power: boseOn ? 'off' : 'on',
                volume: bose.volume ?? 25,
                playing: false,
              })
            }
          />
        </View>
        {boseOn && (
          <>
            <View style={layout.gap}>
              <Button
                label={bose.playing ? 'Pause' : 'Play'}
                onPress={() =>
                  sendCommand('bose', {
                    power: 'on',
                    volume: bose.volume ?? 25,
                    playing: !bose.playing,
                  })
                }
              />
            </View>
            <Tune
              label={`Volume · ${bose.volume ?? 0}`}
              min={0}
              max={100}
              step={5}
              value={bose.volume ?? 20}
              onDone={(v) =>
                sendCommand('bose', {
                  power: 'on',
                  volume: Math.round(v),
                  playing: !!bose.playing,
                })
              }
            />
          </>
        )}
      </Card>

      {/* ---- CURTAIN ---- */}
      <Card>
        <View style={layout.rowSpread}>
          <Text style={text.strong}>Curtain</Text>
          <Chip label={`${curtain.open_pct ?? 0}% open`} />
        </View>
        <Tune
          label="Open"
          min={0}
          max={100}
          step={5}
          value={curtain.open_pct ?? 0}
          onDone={(v) => sendCommand('curtain', { open_pct: Math.round(v) })}
        />
      </Card>

      {/* ---- GUEST ACTIONS ---- */}
      {isGuest && (
        <View style={{ marginTop: 20, gap: 10 }}>
          <Button label="Check out" kind="danger" onPress={askCheckOut} />
          <Button label="Sign out" kind="ghost" onPress={signOut} />
        </View>
      )}

      {/* keeps the last card clear of the bottom tab bar */}
      <View style={{ height: 96 }} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  tiles: { flexDirection: 'row', gap: 10, marginTop: 12 },
  tile: {
    flex: 1,
    backgroundColor: brand.surface,
    borderWidth: 1,
    borderColor: brand.border,
    borderRadius: 16,
    paddingVertical: 16,
    paddingHorizontal: 8,
    alignItems: 'center',
    gap: 6,
  },
  tileIcon: { color: brand.amber, fontSize: 20 },
  tileText: { color: brand.text, fontSize: 13, fontWeight: '600', textAlign: 'center' },
  big: { color: brand.text, fontSize: 40, fontWeight: '800', marginTop: 10 },
  sliderLabel: { color: brand.muted, fontSize: 12, marginBottom: 2, letterSpacing: 0.5 },
  slider: { width: '100%', height: 36 },
});
