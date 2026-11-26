import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { light } from '@/lib/brand';
import { getTrip } from '@/lib/session';
import {
  GBanner,
  GCard,
  GField,
  GScreen,
  PrimaryButton,
  TopBar,
} from '@/components/guest-ui';

export default function ProfileScreen() {
  const [guestId, setGuestId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        setError(e.message ?? 'Could not load your profile');
      }
    })();
  }, []);

  async function save() {
    if (!guestId) return;
    if (!name.trim()) {
      setError('Please enter your name.');
      return;
    }
    setError(null);
    try {
      const g = await api<{ name: string }>(`/guests/${guestId}`, {
        method: 'PATCH',
        body: { name: name.trim() },
      });
      setName(g.name);
      setSaved(true);
    } catch (e: any) {
      setError(e.message ?? 'Could not save. Please try again.');
    }
  }

  return (
    <GScreen>
      <TopBar onBack={() => router.back()} />
      <Text style={styles.title}>Profile</Text>

      <GCard>
        <GField
          label="Full name"
          value={name}
          onChangeText={(t) => {
            setName(t);
            setSaved(false);
          }}
          autoCapitalize="words"
          autoComplete="name"
        />
        <View style={{ marginTop: 14 }}>
          <Text style={styles.label}>Email</Text>
          <Text style={styles.readonly}>{email || '—'}</Text>
        </View>
      </GCard>

      {error && <GBanner text={error} />}
      {saved && <Text style={styles.ok}>Saved.</Text>}

      <View style={{ marginTop: 18 }}>
        <PrimaryButton label="Save" onPress={save} />
      </View>
    </GScreen>
  );
}

const styles = StyleSheet.create({
  title: { color: light.ink, fontSize: 30, fontWeight: '800' },
  label: { color: light.muted, fontSize: 13, fontWeight: '600', marginBottom: 6 },
  readonly: {
    color: light.muted,
    backgroundColor: light.soft,
    borderRadius: 12,
    paddingVertical: 13,
    paddingHorizontal: 14,
    fontSize: 16,
    overflow: 'hidden',
  },
  ok: { color: light.ok, fontWeight: '700', marginTop: 14 },
});
