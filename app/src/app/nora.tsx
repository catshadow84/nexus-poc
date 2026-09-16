import { useState, useRef, useEffect } from 'react';
import {
  Text, View, TextInput, Pressable, ScrollView, StyleSheet,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { router } from 'expo-router';

const BACKEND = 'http://10.21.152.142:8000';

type Message = {
  role: 'user' | 'nora';
  text: string;
  actions?: any[];
};

export default function NoraScreen() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'nora',
      text: "Hi, I'm NORA. Ask me to control the room, order something, or check you out.",
    },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  const [guestName, setGuestName] = useState<string | null>(null);
const [bookingId, setBookingId] = useState<string | null>(null);

useEffect(() => {
  console.log('NORA: fetching active booking...');
  fetch(`${BACKEND}/bookings/active`)
    .then((r) => {
      console.log('NORA: active status', r.status);
      return r.json();
    })
    .then((b) => {
      console.log('NORA: active payload', b);
      if (b && b.id) {
        setBookingId(b.id);
        fetch(`${BACKEND}/guests/${b.guest_id}`)
          .then((r) => {
            console.log('NORA: guest status', r.status);
            return r.json();
          })
          .then((g) => {
            console.log('NORA: guest payload', g);
            setGuestName(g.name);
            setMessages([
              {
                role: 'nora',
                text: `Hi ${g.name.split(' ')[0]}, welcome back. What can I do for you?`,
              },
            ]);
          })
          .catch((e) => console.log('NORA: guest fetch error', e));
      } else {
        console.log('NORA: no active booking');
      }
    })
    .catch((e) => console.log('NORA: active fetch error', e));
}, []);
  useEffect(() => {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text }]);
    setBusy(true);
    try {
      const res = await fetch(`${BACKEND}/nora/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: 'demo', message: text, booking_id: bookingId }),
      });
      const data = await res.json();
      setMessages((m) => [
        ...m,
        { role: 'nora', text: data.reply ?? '(no reply)', actions: data.actions },
      ]);
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: 'nora', text: `Error: ${e.message ?? String(e)}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹ Back</Text>
        </Pressable>
        <Text style={styles.title}>
  NORA{guestName ? ` · ${guestName.split(' ')[0]}` : ''}
</Text>
        <View style={styles.back} />
      </View>

      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        contentContainerStyle={styles.scrollInner}
      >
        {messages.map((m, i) => (
          <View
            key={i}
            style={[
              styles.bubble,
              m.role === 'user' ? styles.userBubble : styles.noraBubble,
            ]}
          >
            <Text style={m.role === 'user' ? styles.userText : styles.noraText}>
              {m.text}
            </Text>
            {m.actions && m.actions.length > 0 && (
              <Text style={styles.actionsText}>
                {m.actions.map((a) => `· ${a.tool}`).join('\n')}
              </Text>
            )}
          </View>
        ))}
      </ScrollView>

      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Ask NORA…"
          placeholderTextColor="#555"
          onSubmitEditing={send}
          returnKeyType="send"
        />
        <Pressable
          style={[styles.sendBtn, (!input.trim() || busy) && styles.sendBtnDisabled]}
          onPress={send}
          disabled={!input.trim() || busy}
        >
          <Text style={styles.sendText}>{busy ? '…' : '↑'}</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0a0a0a' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 60,
    paddingHorizontal: 20,
    paddingBottom: 16,
  },
  back: { width: 60 },
  backText: { color: '#888', fontSize: 16 },
  title: { color: '#fff', fontSize: 16, letterSpacing: 4, fontWeight: '600' },
  scroll: { flex: 1 },
  scrollInner: { padding: 20, paddingTop: 8 },
  bubble: {
    padding: 14,
    borderRadius: 16,
    marginBottom: 10,
    maxWidth: '85%',
  },
  userBubble: { backgroundColor: '#fff', alignSelf: 'flex-end' },
  noraBubble: { backgroundColor: '#1a1a1a', alignSelf: 'flex-start' },
  userText: { color: '#000', fontSize: 15 },
  noraText: { color: '#e5e5e5', fontSize: 15 },
  actionsText: {
    color: '#4ade80',
    fontSize: 11,
    marginTop: 8,
    letterSpacing: 1,
  },
  inputRow: {
    flexDirection: 'row',
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: '#1a1a1a',
    alignItems: 'center',
  },
  input: {
    flex: 1,
    backgroundColor: '#141414',
    color: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 24,
    fontSize: 15,
  },
  sendBtn: {
    marginLeft: 10,
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: { opacity: 0.3 },
  sendText: { color: '#000', fontSize: 20, fontWeight: '600' },
});