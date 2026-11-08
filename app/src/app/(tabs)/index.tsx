import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Text, View, StyleSheet, Pressable, ScrollView, Alert,
} from 'react-native';
import Slider from '@react-native-community/slider';
import { router, useFocusEffect } from 'expo-router';
import { WS_URL } from '@/config';
import { api } from '@/lib/api';
import { clearToken, getToken, getTrip } from '@/lib/session';


async function doCheckout(bookingId: string, onSuccess: (id: string) => void) {
  try {
    await api(`/bookings/${bookingId}/checkout`, { method: 'POST' });
    onSuccess(bookingId);
  } catch (e: any) {
    Alert.alert('Checkout failed', e.message ?? 'Is the backend running?');
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
  const [isGuest, setIsGuest] = useState(false);
  const [guestName, setGuestName] = useState<string | null>(null);
  const [state, setState] = useState<RoomState | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const [bookingId, setBookingId] = useState<string | null>(null);
  const [roomId, setRoomId] = useState<'room1' | 'room2'>('room1');

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
     } catch (e: any) {
       Alert.alert('Rejected', e.message ?? 'Is the backend running?');
     }
   }

   async function runScene(name: string) {
     try {
       await api(`/rooms/${roomId}/scenes/${name}`, { method: 'POST' });
     } catch (e: any) {
       Alert.alert('Scene failed', e.message ?? 'Is the backend running?');
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
      {!isGuest && (<View style={styles.roomRow}>
  {(['room1', 'room2'] as const).map((r) => (
    <Pressable
      key={r}
      style={[styles.roomPill, roomId === r && styles.roomPillActive]}
      onPress={() => setRoomId(r)}
    >
      <Text style={[styles.roomLabel, roomId === r && styles.roomLabelActive]}>
        Room {r.replace('room', '')}
      </Text>
    </Pressable>
  ))}
</View>)}
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

   <Pressable onPress={signOut} style={styles.signOutBtn}>
     <Text style={styles.signOutText}>Sign out</Text>
   </Pressable>

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
    onPress={() => router.push(`/nora?room_id=${roomId}`)}
  >
    <Text style={styles.actionLabel}>Ask NORA</Text>
    <Text style={styles.actionIcon}>◉</Text>
  </Pressable>
  <Pressable
    style={styles.actionBtn}
    onPress={() => router.push(`/booking?room_id=${roomId}`)}
  >
    <Text style={styles.actionLabel}>Book a stay</Text>
    <Text style={styles.actionIcon}>→</Text>
  </Pressable>
</View>

      {isGuest && (
        <View style={styles.actionRow}>
          <Pressable
            style={[styles.actionBtn, styles.actionBtnLeft]}
            onPress={() => router.push('/services')}
          >
            <Text style={styles.actionLabel}>Room service</Text>
            <Text style={styles.actionIcon}>☕︎</Text>
          </Pressable>
          <Pressable
            style={styles.actionBtn}
            onPress={() => router.push(bookingId ? `/summary?booking_id=${bookingId}` : '/trips')}
          >
            <Text style={styles.actionLabel}>My bill</Text>
            <Text style={styles.actionIcon}>≡</Text>
          </Pressable>
        </View>
      )}
      {!isGuest && (
        <Pressable style={styles.checkoutBtn} onPress={() => router.push('/staff')}>
          <Text style={styles.checkoutText}>Staff desk</Text>
        </Pressable>
      )}      

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
  roomRow: {
  flexDirection: 'row',
  gap: 8,
  marginBottom: 16,
  marginTop: -12,
},
roomPill: {
  flex: 1,
  paddingVertical: 8,
  borderRadius: 20,
  borderWidth: 1,
  borderColor: '#333',
  alignItems: 'center',
},
roomPillActive: {
  backgroundColor: '#fff',
  borderColor: '#fff',
},
roomLabel: {
  color: '#888',
  fontSize: 12,
  letterSpacing: 2,
},
roomLabelActive: {
  color: '#000',
  fontWeight: '700',
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
   signOutBtn: { alignSelf: 'flex-end', paddingVertical: 6, paddingHorizontal: 4 },
   signOutText: { color: '#8a94a3', fontSize: 12, letterSpacing: 1 },
});