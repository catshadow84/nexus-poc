import { useEffect, useState } from 'react';
import { Alert, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { api } from '@/lib/api';
import { brand } from '@/lib/brand';
import { getTrip } from '@/lib/session';
import { Banner, Button, Card, Header, Screen, layout, text } from '@/components/ui';

type MenuItem = { item: string; price_cents: number };

function titleCase(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function ServicesScreen() {
  const params = useLocalSearchParams<{ booking_id?: string }>();
  const [items, setItems] = useState<MenuItem[]>([]);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [currency, setCurrency] = useState('USD');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api<{ items: MenuItem[] }>('/menu')
      .then((d) => setItems(d.items))
      .catch((e) => Alert.alert('Could not load the menu', e.message));
    // Show prices in the currency of this stay, the same one NORA and the receipt use.
    (async () => {
      try {
        const id = params.booking_id ?? (await getTrip())?.bookingId;
        if (!id) return;
        const b = await api<{ currency?: string | null }>(`/bookings/${id}`);
        if (b.currency) setCurrency(b.currency);
      } catch {
        // keep the default
      }
    })();
  }, [params.booking_id]);

  const q = (item: string) => qty[item] ?? 1;
  const change = (item: string, delta: number) =>
    setQty((s) => ({ ...s, [item]: Math.min(10, Math.max(1, (s[item] ?? 1) + delta)) }));
  const price = (cents: number) => `${(cents / 100).toFixed(2)} ${currency}`;

  async function order(item: string) {
    const bookingId = params.booking_id ?? (await getTrip())?.bookingId;
    if (!bookingId) {
      Alert.alert('Guests only', 'Sign in as a guest with an active stay to order.');
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await api(`/bookings/${bookingId}/orders`, {
        method: 'POST',
        body: { item, quantity: q(item) },
      });
      setMessage(`Ordered ${q(item)} × ${item}. It is on the bill.`);
    } catch (e: any) {
      Alert.alert('Could not order', e.message ?? 'Something went wrong');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Header title="Room service" subtitle="Added to the bill of this stay." onBack={() => router.back()} />

      {message && <Banner tone="ok" text={message} />}

      {items.map((m) => (
        <Card key={m.item}>
          <View style={layout.rowSpread}>
            <View style={{ flex: 1 }}>
              <Text style={text.strong}>{titleCase(m.item)}</Text>
              <Text style={text.muted}>{price(m.price_cents)} each</Text>
            </View>
            <View style={layout.row}>
              <Button small kind="ghost" label="−" onPress={() => change(m.item, -1)} />
              <Text style={{ color: brand.text, fontSize: 16, minWidth: 20, textAlign: 'center' }}>{q(m.item)}</Text>
              <Button small kind="ghost" label="+" onPress={() => change(m.item, 1)} />
            </View>
          </View>
          <View style={layout.gap}>
            <Button
              small
              label={busy ? 'Ordering…' : `Order · ${price(m.price_cents * q(m.item))}`}
              disabled={busy}
              onPress={() => order(m.item)}
            />
          </View>
        </Card>
      ))}
    </Screen>
  );
}
