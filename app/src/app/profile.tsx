import { useEffect, useState } from 'react';
import { Text, View, TextInput, Pressable, StyleSheet, Alert } from 'react-native';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { getTrip } from '@/lib/session';

export default function ProfileScreen() {
  const [guestId, setGuestId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    (async () => {
      const trip = await getTrip();
      if (!trip) {
        router.replace('/search');
        return;
      }
      setGuestId(trip.guestId);
      try {
        const g = await api<{ name: string; email: string }>(`/guests/${trip.guestId}`);
        setName(g.name);
        setEmail(g.email);
      } catch (e: any) {
        Alert.alert('Could not load your profile', e.message);
      }
    })();
  }, []);

  async function save() {
    if (!guestId || !name.trim()) return;
    try {
      const g = await api<{ name: string }>(`/guests/${guestId}`, {
        method: 'PATCH',
        body: { name: name.trim() },
      });
      setName(g.name);
      setSaved(true);
    } catch (e: any) {
      Alert.alert('Could not save', e.message ?? 'Something went wrong');
    }
  }

  return (
    <View style={styles.root}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.subtitle}>PROFILE</Text>

      <Text style={styles.label}>Name</Text>
      <TextInput
        style={styles.input}
        value={name}
        onChangeText={(t) => {
          setName(t);
          setSaved(false);
        }}
        autoCapitalize="words"
      />
      <Text style={styles.label}>Email</Text>
      <Text style={styles.readonly}>{email}</Text>

      <Pressable style={styles.btn} onPress={save}>
        <Text style={styles.btnText}>Save</Text>
      </Pressable>
      {saved && <Text style={styles.ok}>Saved.</Text>}

      <Pressable style={styles.secondary} onPress={() => router.back()}>
        <Text style={styles.secondaryText}>Back</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0a0a0a', padding: 24, paddingTop: 72 },
  brand: { color: '#fff', fontSize: 36, fontWeight: 'bold', letterSpacing: 8 },
  subtitle: { color: '#888', marginTop: 8, marginBottom: 24, letterSpacing: 2 },
  label: { color: '#666', fontSize: 12, letterSpacing: 1, marginBottom: 4 },
  input: { backgroundColor: '#141414', color: '#fff', borderRadius: 10, padding: 14, marginBottom: 16 },
  readonly: { color: '#888', padding: 14, backgroundColor: '#101010', borderRadius: 10, marginBottom: 16 },
  btn: { backgroundColor: '#fff', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 8 },
  btnText: { color: '#000', fontWeight: '600', letterSpacing: 1 },
  ok: { color: '#4ade80', marginTop: 12 },
  secondary: { borderWidth: 1, borderColor: '#333', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 20 },
  secondaryText: { color: '#fff', letterSpacing: 1 },
});