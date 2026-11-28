import { useEffect, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { api } from '@/lib/api';
import { brand } from '@/lib/brand';
import { getTrip } from '@/lib/session';

type Action = { tool: string; result?: any };

type Message = {
  role: 'user' | 'nora';
  text: string;
  actions?: Action[];
};

const SUGGESTIONS = [
  "I'm cold",
  'Goodnight',
  'Order a coffee',
  'Menu',
  "What's my bill?",
  'Check me out',
];

const ACTION_LABEL: Record<string, string> = {
  set_light: 'Light updated',
  set_central_ac: 'Air conditioning updated',
  set_thermostat: 'Air conditioning updated',
  set_bose: 'Music updated',
  set_curtain: 'Curtain updated',
  create_service_order: 'Order placed',
  checkout: 'Checked out',
};

function actionLines(actions?: Action[]): string[] {
  const seen = new Set<string>();
  for (const a of actions ?? []) seen.add(ACTION_LABEL[a.tool] ?? a.tool);
  return [...seen];
}

export default function NoraScreen() {
  const params = useLocalSearchParams<{ room_id?: string }>();
  const roomId = params.room_id ?? 'room1';
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'nora',
      text: "Hi, I'm NORA. Ask me to change the room, order something, show your bill or check you out.",
    },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [guestName, setGuestName] = useState<string | null>(null);
  const [bookingId, setBookingId] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    api<{ id?: string; guest_id?: string } | null>(`/bookings/active?room_id=${roomId}`)
      .then(async (b) => {
        if (b && b.id && b.guest_id) {
          setBookingId(b.id);
          const g = await api<{ name: string }>(`/guests/${b.guest_id}`);
          setGuestName(g.name);
          setMessages([
            { role: 'nora', text: `Hi ${g.name.split(' ')[0]}, welcome back. What can I do for you?` },
          ]);
        }
      })
      .catch(() => {
        // NORA still works without the name; she just will not greet the guest by it
      });
  }, [roomId]);

  useEffect(() => {
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    return () => clearTimeout(t);
  }, [messages]);

  async function send(raw?: string) {
    const text = (raw ?? input).trim();
    if (!text || busy) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text }]);
    setBusy(true);
    try {
      const data = await api<{
        reply?: string;
        actions?: Action[];
        booking_id?: string | null;
        guest_name?: string | null;
      }>('/nora/chat', {
        method: 'POST',
        body: { session_id: 'demo', message: text, booking_id: bookingId, room_id: roomId },
      });
      setMessages((m) => [
        ...m,
        { role: 'nora', text: data.reply ?? 'Sorry, I have no answer for that.', actions: data.actions },
      ]);
      if (data.guest_name && !guestName) setGuestName(data.guest_name);
      if (data.actions?.some((a) => a.tool === 'checkout')) {
        // The server tells us which booking was checked out, so this works even
        // when the screen could not look the booking up when it opened.
        const id = data.booking_id ?? bookingId ?? (await getTrip())?.bookingId;
        if (id) setTimeout(() => router.replace(`/summary?booking_id=${id}`), 800);
      }
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: 'nora', text: e.message ?? 'I could not reach the server. Please try again.' },
      ]);
    } finally {
      setBusy(false);
    }
  }

  const last = messages[messages.length - 1];
  const askedToConfirm = last?.role === 'nora' && /yes, check me out/i.test(last.text);
  const chips = askedToConfirm ? ['Yes, check me out', 'No, stay'] : SUGGESTIONS;

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.back} accessibilityRole="button">
          <Text style={styles.backText}>‹ Back</Text>
        </Pressable>
        <Text style={styles.title}>NORA{guestName ? ` · ${guestName.split(' ')[0]}` : ''}</Text>
        <View style={styles.back} />
      </View>

      <ScrollView ref={scrollRef} style={styles.scroll} contentContainerStyle={styles.scrollInner}>
        {messages.map((m, i) => {
          const lines = actionLines(m.actions);
          return (
            <View
              key={i}
              style={[styles.bubble, m.role === 'user' ? styles.userBubble : styles.noraBubble]}
            >
              <Text style={m.role === 'user' ? styles.userText : styles.noraText}>{m.text}</Text>
              {lines.length > 0 && (
                <Text style={styles.actionsText}>{lines.map((l) => `✓ ${l}`).join('\n')}</Text>
              )}
            </View>
          );
        })}
        {busy && (
          <View style={[styles.bubble, styles.noraBubble]}>
            <Text style={styles.noraText}>…</Text>
          </View>
        )}
      </ScrollView>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipsRow}
        contentContainerStyle={{ paddingHorizontal: 16, gap: 8 }}
        keyboardShouldPersistTaps="handled"
      >
        {chips.map((c) => (
          <Pressable
            key={c}
            onPress={() => (c === 'No, stay' ? send('No, I will stay') : send(c))}
            disabled={busy}
            style={[styles.chip, busy && { opacity: 0.4 }]}
            accessibilityRole="button"
          >
            <Text style={styles.chipText}>{c}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Ask NORA…"
          placeholderTextColor={brand.muted}
          onSubmitEditing={() => send()}
          returnKeyType="send"
        />
        <Pressable
          style={[styles.sendBtn, (!input.trim() || busy) && styles.sendBtnDisabled]}
          onPress={() => send()}
          disabled={!input.trim() || busy}
          accessibilityRole="button"
          accessibilityLabel="Send"
        >
          <Text style={styles.sendText}>↑</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: brand.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 56,
    paddingHorizontal: 20,
    paddingBottom: 14,
  },
  back: { width: 70 },
  backText: { color: brand.muted, fontSize: 16 },
  title: { color: brand.text, fontSize: 16, letterSpacing: 4, fontWeight: '700' },
  scroll: { flex: 1 },
  scrollInner: { padding: 20, paddingTop: 8, width: '100%', maxWidth: 760, alignSelf: 'center' },
  bubble: { padding: 14, borderRadius: 16, marginBottom: 10, maxWidth: '85%' },
  userBubble: { backgroundColor: brand.amber, alignSelf: 'flex-end' },
  noraBubble: {
    backgroundColor: brand.surface,
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: brand.border,
  },
  userText: { color: brand.onAmber, fontSize: 15, lineHeight: 21 },
  noraText: { color: brand.text, fontSize: 15, lineHeight: 21 },
  actionsText: { color: brand.ok, fontSize: 12, marginTop: 8, fontWeight: '600', lineHeight: 18 },
  chipsRow: { flexGrow: 0, paddingVertical: 8 },
  chip: {
    borderWidth: 1,
    borderColor: brand.border,
    backgroundColor: brand.surfaceSoft,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
  },
  chipText: { color: brand.text, fontSize: 14, fontWeight: '600' },
  inputRow: {
    flexDirection: 'row',
    padding: 16,
    paddingBottom: 24,
    borderTopWidth: 1,
    borderTopColor: brand.border,
    alignItems: 'center',
  },
  input: {
    flex: 1,
    backgroundColor: brand.surfaceSoft,
    color: brand.text,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 24,
    fontSize: 15,
    borderWidth: 1,
    borderColor: brand.border,
  },
  sendBtn: {
    marginLeft: 10,
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: brand.amber,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: { opacity: 0.4 },
  sendText: { color: brand.onAmber, fontSize: 20, fontWeight: '800' },
});
