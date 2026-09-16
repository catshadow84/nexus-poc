import { useEffect, useRef, useState } from 'react';
import {
  Text, View, StyleSheet, Pressable, ScrollView, Alert,
} from 'react-native';
import Slider from '@react-native-community/slider';
import { router } from 'expo-router';

const BACKEND_HTTP = 'http://192.168.10.30:8000';
const BACKEND_WS = 'ws://192.168.10.30:8000/ws';

async function doCheckout(bookingId: string, onSuccess: (id: string) => void) {
  try {
    const res = await fetch(`${BACKEND_HTTP}/bookings/${bookingId}/checkout`, {
      method: 'POST',
    });
    if (!res.ok) {
      const text = await res.text();
      Alert.alert('Checkout failed', text.slice(0, 240));
      return;
    }
    onSuccess(bookingId);
  } catch {
    Alert.alert('Network error', 'Is the backend running?');
  }
}
async function runScene(name: string) {
  try {
    const res = await fetch(`${BACKEND_HTTP}/rooms/room1/scenes/${name}`, {
      method: 'POST',
    });
    if (!res.ok) {
      const text = await res.text();
      Alert.alert('Scene failed', text.slice(0, 240));
    }
  } catch {
    Alert.alert('Network error', 'Is the backend running?');
  }
}

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

export default function HomeScreen() {
  const [guestName, setGuestName] = useState<string | null>(null);
  const [state, setState] = useState<RoomState | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const [bookingId, setBookingId] = useState<string | null>(null);

  useEffect(() => {
    // initial state fetch
    fetch(`${BACKEND_HTTP}/rooms/room1/state`)
      .then((r) => r.json())
      .then(setState)
      .catch((e) => console.warn('initial fetch failed', e));

    // websocket for live updates
    const ws = new WebSocket(BACKEND_WS);
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
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
    fetch(`${BACKEND_HTTP}/bookings/active?room_id=room1`)
  .then((r) => r.json())
  .then((b) => {
    if (b && b.id) {
      setBookingId(b.id);
      fetch(`${BACKEND_HTTP}/guests/${b.guest_id}`)
        .then((r) => r.json())
        .then((g) => setGuestName(g.name))
        .catch(() => {});
    } else {
      setGuestName(null);
      setBookingId(null);
    }
  })
  .catch(() => {});
    return () => { ws.close(); };
  }, []);

  async function sendCommand(device: string, value: Record<string, any>) {
    try {
      const res = await fetch(`${BACKEND_HTTP}/rooms/room1/device/${device}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(value),
      });
      console.log('POST /room/' + device + '/command', res.status);
      if (!res.ok) {
        const text = await res.text();
        Alert.alert('Rejected', text.slice(0, 240));
      }
    } catch (err) {
      Alert.alert('Network error', 'Is the backend running?');
    }
  }

  if (!state || !state.devices) {
  return (
    <View style={styles.center}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.muted}>connecting…</Text>
    </View>
  );
}

  const light = state.devices.light?.reported ?? {};
  const thermo = state.devices.thermostat?.reported ?? {};
  const curtain = state.devices.curtain?.reported ?? {};

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollInner}>
      <View style={styles.header}>
        <Text style={styles.brand}>NEXUS</Text>
        <Text style={[styles.dot, connected ? styles.dotOn : styles.dotOff]}>
          {connected ? '● live' : '○ offline'}
        </Text>
      </View>
      {guestName && (
  <Text style={styles.welcome}>Welcome, {guestName}</Text>
)}
{guestName && (
  <Pressable
    style={styles.checkoutBtn}
    onPress={() => {
      if (bookingId) {
        doCheckout(bookingId, (id) => router.push(`/summary?booking_id=${id}`));
      }
    }}
  >
    <Text style={styles.checkoutText}>Check out</Text>
  </Pressable>
)}


      <View style={styles.sceneRow}>
  <Pressable style={styles.sceneBtn} onPress={() => runScene('good_morning')}>
    <Text style={styles.sceneLabel}>Good morning</Text>
    <Text style={styles.sceneIcon}>☀︎</Text>
  </Pressable>

  <Pressable style={styles.sceneBtn} onPress={() => runScene('focus')}>
    <Text style={styles.sceneLabel}>Focus</Text>
    <Text style={styles.sceneIcon}>◆</Text>
  </Pressable>

  <Pressable style={styles.sceneBtn} onPress={() => runScene('goodnight')}>
    <Text style={styles.sceneLabel}>Goodnight</Text>
    <Text style={styles.sceneIcon}>☾</Text>
  </Pressable>
</View>

      <View style={styles.actionRow}>
  <Pressable
    style={[styles.actionBtn, styles.actionBtnLeft]}
    onPress={() => router.push('/nora')}
  >
    <Text style={styles.actionLabel}>Ask NORA</Text>
    <Text style={styles.actionIcon}>◉</Text>
  </Pressable>
  <Pressable
    style={styles.actionBtn}
    onPress={() => router.push('/booking')}
  >
    <Text style={styles.actionLabel}>Book a stay</Text>
    <Text style={styles.actionIcon}>→</Text>
  </Pressable>
</View>

      {/* ---- LIGHT ---- */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Light</Text>
        <Text style={styles.value}>
          {light.power === 'on'
            ? `On · ${light.brightness ?? 0}% · ${light.color ?? 'neutral'}`
            : 'Off'}
        </Text>

        <Pressable
          style={[styles.btn, light.power === 'on' && styles.btnActive]}
          onPress={() =>
  sendCommand('light', {
    power: light.power === 'on' ? 'off' : 'on',
    brightness: light.brightness || 80,
    color: 'warm',  // was: light.color || 'warm'
  })
}
        >
          <Text style={styles.btnText}>
            {light.power === 'on' ? 'Turn Off' : 'Turn On'}
          </Text>
        </Pressable>

        <Text style={styles.sliderLabel}>Brightness</Text>
        <Slider
          style={styles.slider}
          minimumValue={0}
          maximumValue={100}
          step={5}
          value={light.brightness ?? 0}
          onSlidingComplete={(v) =>
            sendCommand('light', {
              power: 'on',
              brightness: Math.round(v),
              color: light.color || 'warm',
            })
          }
        />

        <View style={styles.row}>
          {(['warm', 'neutral', 'cool'] as const).map((c) => (
            <Pressable
              key={c}
              style={[styles.chip, light.color === c && styles.chipActive]}
              onPress={() =>
                sendCommand('light', {
                  power: light.power || 'on',
                  brightness: light.brightness || 80,
                  color: c,
                })
              }
            >
              <Text style={styles.chipText}>{c}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      {/* ---- THERMOSTAT ---- */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Thermostat</Text>
        <Text style={styles.value}>
          Now {thermo.current_c ?? '—'}°C · Target {thermo.target_c ?? '—'}°C · {thermo.mode ?? 'cool'}
        </Text>

        <Text style={styles.sliderLabel}>Target temperature</Text>
        <Slider
          style={styles.slider}
          minimumValue={16}
          maximumValue={30}
          step={0.5}
          value={thermo.target_c ?? 22}
          onSlidingComplete={(v) =>
            sendCommand('thermostat', {
              target_c: Number(v.toFixed(1)),
              mode: thermo.mode || 'cool',
            })
          }
        />
      </View>

      {/* ---- CURTAIN ---- */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Curtain</Text>
        <Text style={styles.value}>{curtain.open_pct ?? 0}% open</Text>

        <Text style={styles.sliderLabel}>Open percentage</Text>
        <Slider
          style={styles.slider}
          minimumValue={0}
          maximumValue={100}
          step={5}
          value={curtain.open_pct ?? 0}
          onSlidingComplete={(v) =>
            sendCommand('curtain', { open_pct: Math.round(v) })
          }
        />
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  actionRow: { flexDirection: 'row', marginBottom: 20, gap: 8 },
actionBtn: {
  flex: 1,
  backgroundColor: '#141414',
  borderWidth: 1,
  borderColor: '#222',
  borderRadius: 12,
  paddingVertical: 14,
  alignItems: 'center',
},
actionBtnLeft: {},
actionLabel: { color: '#fff', fontSize: 13, letterSpacing: 1, marginBottom: 4 },
actionIcon: { color: '#888', fontSize: 16 },
  sceneRow: {
  flexDirection: 'row',
  gap: 8,
  marginBottom: 20,
},
sceneBtn: {
  flex: 1,
  backgroundColor: '#141414',
  borderWidth: 1,
  borderColor: '#222',
  borderRadius: 12,
  paddingVertical: 14,
  alignItems: 'center',
},
sceneLabel: {
  color: '#fff',
  fontSize: 12,
  letterSpacing: 1,
  marginBottom: 4,
},
sceneIcon: {
  color: '#888',
  fontSize: 18,
},
  scroll: { flex: 1, backgroundColor: '#0a0a0a' },
  scrollInner: { padding: 20, paddingTop: 60 },
  center: {
    flex: 1, backgroundColor: '#0a0a0a',
    alignItems: 'center', justifyContent: 'center',
  },
  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'baseline', marginBottom: 24,
  },
  brand: {
    color: '#fff', fontSize: 32, fontWeight: 'bold',
    letterSpacing: 6,
  },
  muted: { color: '#666', marginTop: 12, letterSpacing: 2 },
  dot: { fontSize: 12, letterSpacing: 1 },
  dotOn: { color: '#4ade80' },
  dotOff: { color: '#f87171' },

  welcome: {
    color: '#4ade80',
    fontSize: 13,
    letterSpacing: 1,
    marginTop: -16,
    marginBottom: 20,
  },

  card: {
    backgroundColor: '#141414', borderRadius: 14,
    padding: 18, marginBottom: 16,
    borderWidth: 1, borderColor: '#222',
  },
  cardTitle: {
    color: '#fff', fontSize: 18, fontWeight: '600',
    marginBottom: 6, letterSpacing: 1,
  },
  value: { color: '#aaa', fontSize: 14, marginBottom: 14 },

  btn: {
    backgroundColor: '#fff', paddingVertical: 12,
    borderRadius: 10, alignItems: 'center', marginBottom: 14,
  },
  btnActive: { backgroundColor: '#e5e5e5' },
  btnText: { color: '#000', fontSize: 15, fontWeight: '600', letterSpacing: 1 },

  sliderLabel: { color: '#666', fontSize: 12, marginBottom: 2, letterSpacing: 1 },
  slider: { width: '100%', height: 36 },

  row: { flexDirection: 'row', gap: 8, marginTop: 4 },
  chip: {
    flex: 1, paddingVertical: 8,
    borderRadius: 8, borderWidth: 1, borderColor: '#333',
    alignItems: 'center',
  },
  chipActive: { backgroundColor: '#fff', borderColor: '#fff' },
  chipText: { color: '#888', fontSize: 12, letterSpacing: 1 },
  checkoutBtn: {
  backgroundColor: '#1a1a1a',
  borderWidth: 1,
  borderColor: '#333',
  borderRadius: 10,
  paddingVertical: 10,
  alignItems: 'center',
  marginTop: -12,
  marginBottom: 20,
},
checkoutText: {
  color: '#f87171',
  fontSize: 13,
  letterSpacing: 1,
},
});