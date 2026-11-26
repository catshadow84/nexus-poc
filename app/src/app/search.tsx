import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { light } from '@/lib/brand';
import { addDays, money, nightsBetween, prettyDate, toIso } from '@/lib/dates';
import { heroPhoto, roomPhoto } from '@/lib/rooms';
import { hasSeenWelcome } from '@/lib/session';
import {
  Calendar,
  GBanner,
  GCard,
  GScreen,
  PrimaryButton,
  Stepper,
  TopBar,
} from '@/components/guest-ui';

type Offer = {
  rate_plan_id: string;
  room_type: string | null;
  rate_plan: string | null;
  total_amount: number;
  currency: string;
  guarantee: string | null;
  available_units: number | null;
  bookable: boolean;
};

type Group = { roomType: string; offers: Offer[] };

export default function SearchScreen() {
  const [start, setStart] = useState<string | null>(addDays(toIso(new Date()), 30));
  const [end, setEnd] = useState<string | null>(addDays(toIso(new Date()), 32));
  const [adults, setAdults] = useState(2);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [offers, setOffers] = useState<Offer[] | null>(null);
  const [searchedNights, setSearchedNights] = useState(0);
  const [searchedAdults, setSearchedAdults] = useState(2);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // First time on this device: show the three intro slides.
  useEffect(() => {
    hasSeenWelcome().then((seen) => {
      if (!seen) router.replace('/welcome');
    });
  }, []);

  const nights = start && end ? nightsBetween(start, end) : 0;

  const groups: Group[] = useMemo(() => {
    const map = new Map<string, Offer[]>();
    for (const o of offers ?? []) {
      const key = o.room_type ?? 'Room';
      map.set(key, [...(map.get(key) ?? []), o]);
    }
    const list = [...map.entries()].map(([roomType, items]) => ({
      roomType,
      offers: [...items].sort((a, b) => a.total_amount - b.total_amount),
    }));
    return list.sort((a, b) => a.offers[0].total_amount - b.offers[0].total_amount);
  }, [offers]);

  function changeDates(newStart: string | null, newEnd: string | null) {
    setStart(newStart);
    setEnd(newEnd);
    if (newStart && newEnd) setCalendarOpen(false);
  }

  async function search() {
    if (!start || !end) return;
    setError(null);
    setOffers(null);
    setPicked({});
    setLoading(true);
    try {
      const data = await api<Offer[]>(`/offers?arrival=${start}&departure=${end}&adults=${adults}`);
      setSearchedNights(nights);
      setSearchedAdults(adults);
      setOffers(data);
    } catch (e: any) {
      setError(e.message ?? 'Search failed. Is the server running?');
    } finally {
      setLoading(false);
    }
  }

  function chosenOffer(group: Group): Offer {
    const id = picked[group.roomType];
    return (
      group.offers.find((o) => o.rate_plan_id === id) ??
      group.offers.find((o) => o.bookable) ??
      group.offers[0]
    );
  }

  function reserve(o: Offer) {
    if (!start || !end) return;
    router.push({
      pathname: '/reserve',
      params: {
        arrival: start,
        departure: end,
        nights: String(searchedNights),
        adults: String(searchedAdults),
        rate_plan_id: o.rate_plan_id,
        room_type: o.room_type ?? 'Room',
        rate_plan: o.rate_plan ?? '',
        total: String(o.total_amount),
        currency: o.currency,
      },
    });
  }

  const whenLabel =
    start && end
      ? `${prettyDate(start)}  →  ${prettyDate(end)}  ·  ${nights} night${nights === 1 ? '' : 's'}`
      : start
        ? `${prettyDate(start)}  →  pick your departure`
        : 'Pick your arrival date';

  return (
    <GScreen>
      <TopBar
        right={
          <Pressable onPress={() => router.push('/signin')} accessibilityRole="button">
            <Text style={styles.staffLink}>Staff sign in</Text>
          </Pressable>
        }
      />

      <View style={styles.hero}>
        <Image source={heroPhoto} style={styles.heroImage} resizeMode="cover" />
        <View style={styles.heroShade} />
        <View style={styles.heroText}>
          <Text style={styles.heroTitle}>Book. Unlock. Stay.</Text>
          <Text style={styles.heroSub}>Your room and your keys, all in one app.</Text>
        </View>
      </View>

      <GCard>
        <Pressable
          onPress={() => setCalendarOpen(!calendarOpen)}
          accessibilityRole="button"
          style={styles.whenRow}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.small}>WHEN</Text>
            <Text style={styles.when}>{whenLabel}</Text>
          </View>
          <Text style={styles.caret}>{calendarOpen ? '▴' : '▾'}</Text>
        </Pressable>

        {calendarOpen && (
          <View style={{ marginTop: 8 }}>
            <Calendar start={start} end={end} onChange={changeDates} />
            <Text style={styles.hint}>Tap your arrival day, then your departure day. Up to 14 nights.</Text>
          </View>
        )}

        <View style={styles.divider} />
        <Stepper label="Adults" value={adults} min={1} max={6} onChange={setAdults} />

        <View style={{ marginTop: 12 }}>
          <PrimaryButton
            label={loading ? 'Searching…' : 'Check availability'}
            onPress={search}
            disabled={loading || !start || !end}
          />
        </View>
      </GCard>

      {loading && <ActivityIndicator style={{ marginTop: 24 }} color={light.navy} />}
      {error && <GBanner text={error} />}
      {offers && offers.length === 0 && (
        <GBanner tone="info" text="No rooms are available for these dates. Try different dates." />
      )}

      {groups.length > 0 && (
        <Text style={styles.resultsTitle}>
          {groups.length} room type{groups.length === 1 ? '' : 's'} · {searchedNights} night
          {searchedNights === 1 ? '' : 's'} · {searchedAdults} adult{searchedAdults === 1 ? '' : 's'}
        </Text>
      )}

      {groups.map((group) => {
        const chosen = chosenOffer(group);
        const units = group.offers
          .map((o) => o.available_units)
          .filter((n): n is number => n != null);
        const left = units.length ? Math.min(...units) : null;
        return (
          <GCard key={group.roomType} style={{ padding: 0 }}>
            <Image source={roomPhoto(group.roomType)} style={styles.roomPhoto} resizeMode="cover" />
            <View style={{ padding: 16 }}>
              <Text style={styles.roomTitle}>{group.roomType}</Text>
              {left != null && left <= 3 && (
                <Text style={styles.scarce}>
                  {left === 1 ? 'Only 1 left' : `Only ${left} left`}
                </Text>
              )}

              <View style={{ marginTop: 10, gap: 8 }}>
                {group.offers.map((o) => {
                  const on = o.rate_plan_id === chosen.rate_plan_id;
                  return (
                    <Pressable
                      key={o.rate_plan_id}
                      disabled={!o.bookable}
                      onPress={() => setPicked({ ...picked, [group.roomType]: o.rate_plan_id })}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: on }}
                      style={[styles.rate, on && styles.rateOn, !o.bookable && { opacity: 0.5 }]}
                    >
                      <View style={[styles.radio, on && styles.radioOn]}>
                        {on && <View style={styles.radioDot} />}
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.rateName}>{o.rate_plan ?? 'Standard rate'}</Text>
                        {!o.bookable && (
                          <Text style={styles.rateNote}>Needs a card. Real payments come later.</Text>
                        )}
                      </View>
                      <View style={{ alignItems: 'flex-end' }}>
                        <Text style={styles.rateTotal}>{money(o.total_amount, o.currency)}</Text>
                        <Text style={styles.rateNote}>
                          {money(o.total_amount / Math.max(searchedNights, 1), o.currency)} / night
                        </Text>
                      </View>
                    </Pressable>
                  );
                })}
              </View>

              <View style={{ marginTop: 14 }}>
                <PrimaryButton
                  label={`Reserve · ${money(chosen.total_amount, chosen.currency)}`}
                  onPress={() => reserve(chosen)}
                  disabled={!chosen.bookable}
                />
              </View>
            </View>
          </GCard>
        );
      })}
    </GScreen>
  );
}

const styles = StyleSheet.create({
  staffLink: { color: light.muted, fontSize: 14, fontWeight: '600' },
  hero: { height: 220, borderRadius: 20, overflow: 'hidden' },
  heroImage: { width: '100%', height: 220 },
  heroShade: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(15,35,56,0.45)',
  },
  heroText: { position: 'absolute', left: 0, right: 0, bottom: 0, padding: 18 },
  heroTitle: { color: '#fff', fontSize: 30, fontWeight: '800' },
  heroSub: { color: '#E6EEF5', fontSize: 15, marginTop: 4 },
  whenRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 4 },
  small: { color: light.muted, fontSize: 11, fontWeight: '700', letterSpacing: 1 },
  when: { color: light.ink, fontSize: 16, fontWeight: '700', marginTop: 4 },
  caret: { color: light.navy, fontSize: 18, paddingLeft: 12 },
  hint: { color: light.muted, fontSize: 13, marginTop: 8 },
  divider: { height: 1, backgroundColor: light.line, marginVertical: 12 },
  resultsTitle: { color: light.muted, fontSize: 14, fontWeight: '600', marginTop: 22 },
  roomPhoto: { width: '100%', height: 180 },
  roomTitle: { color: light.ink, fontSize: 20, fontWeight: '800' },
  scarce: { color: light.danger, fontSize: 13, fontWeight: '700', marginTop: 4 },
  rate: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderWidth: 1,
    borderColor: light.line,
    borderRadius: 14,
    padding: 12,
    backgroundColor: '#fff',
  },
  rateOn: { borderColor: light.navy, backgroundColor: light.soft },
  radio: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: light.line,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioOn: { borderColor: light.navy },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: light.navy },
  rateName: { color: light.ink, fontSize: 15, fontWeight: '700' },
  rateTotal: { color: light.ink, fontSize: 16, fontWeight: '800' },
  rateNote: { color: light.muted, fontSize: 12, marginTop: 2 },
});