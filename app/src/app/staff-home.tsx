import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { router, useFocusEffect, type Href } from 'expo-router';
import { api } from '@/lib/api';
import { brand, ROLE_LABEL } from '@/lib/brand';
import { clearToken, getStaff, type StaffRole, type StaffSession } from '@/lib/session';
import { Button, Header, Screen, layout } from '@/components/ui';

type Item = { title: string; text: string; href: string };

const FRONT: Item = { title: 'Front desk', text: 'Arrivals, departures, check-in and check-out', href: '/staff' };
const ROOMS: Item = { title: 'Housekeeping', text: 'Which rooms are dirty, being cleaned or ready', href: '/housekeeping' };
const ISSUES: Item = { title: 'Maintenance issues', text: 'Report and track problems in rooms', href: '/maintenance' };
const CONTROLS: Item = { title: 'Room controls', text: 'Lights, air conditioning, music and the door', href: '/?controls=1' };
const TEAM: Item = { title: 'Team', text: 'Staff accounts and roles', href: '/team' };

const MENU: Record<StaffRole, Item[]> = {
  front_desk: [FRONT, ROOMS, ISSUES, CONTROLS],
  housekeeping: [ROOMS, ISSUES],
  maintenance: [ISSUES, CONTROLS],
  manager: [FRONT, ROOMS, ISSUES, CONTROLS, TEAM],
};

export default function StaffHomeScreen() {
  const [staff, setStaffState] = useState<StaffSession | null>(null);

  useFocusEffect(
    useCallback(() => {
      let live = true;
      getStaff().then((s) => {
        if (!live) return;
        if (!s) router.replace('/signin');
        else setStaffState(s);
      });
      return () => {
        live = false;
      };
    }, []),
  );

  async function signOut() {
    try {
      await api('/staff/logout', { method: 'POST' });
    } catch {
      // signing out locally is enough if the server cannot be reached
    }
    await clearToken();
    router.replace('/signin');
  }

  if (!staff) return <Screen><Text style={{ color: brand.muted }}>Loading…</Text></Screen>;

  return (
    <Screen>
      <Header title={`Hi, ${staff.name.split(' ')[0]}`} subtitle={ROLE_LABEL[staff.role]} />
      <View style={styles.grid}>
        {MENU[staff.role].map((item) => (
          <Pressable
            key={item.title}
            style={styles.tile}
            accessibilityRole="button"
            onPress={() => router.push(item.href as Href)}
          >
            <Text style={styles.tileTitle}>{item.title}</Text>
            <Text style={styles.tileText}>{item.text}</Text>
          </Pressable>
        ))}
      </View>
      <View style={layout.gap}>
        <Button label="Sign out" kind="ghost" onPress={signOut} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  tile: {
    flexGrow: 1,
    flexBasis: 280,
    backgroundColor: brand.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: brand.border,
    padding: 18,
    minHeight: 110,
  },
  tileTitle: { color: brand.text, fontSize: 18, fontWeight: '700' },
  tileText: { color: brand.muted, marginTop: 6, lineHeight: 20 },
});