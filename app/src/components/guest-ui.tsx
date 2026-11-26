import { ReactNode, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
} from 'react-native';
import { light } from '@/lib/brand';
import { MONTHS, nightsBetween, toIso } from '@/lib/dates';

/** Light page for the guest booking flow. Centered and narrow so it also looks right in a browser. */
export function GScreen({ children }: { children: ReactNode }) {
  return (
    <View style={s.root}>
      <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
    </View>
  );
}

export function Wordmark({ color = light.navy }: { color?: string }) {
  return (
    <Text style={[s.wordmark, { color }]}>
      nexus<Text style={{ color: light.amber }}>.</Text>
    </Text>
  );
}

export function TopBar({ onBack, right }: { onBack?: () => void; right?: ReactNode }) {
  return (
    <View style={s.topBar}>
      {onBack ? (
        <Pressable onPress={onBack} accessibilityRole="button" style={s.backBtn}>
          <Text style={s.backText}>‹ Back</Text>
        </Pressable>
      ) : (
        <Wordmark />
      )}
      {right}
    </View>
  );
}

export function GCard({ children, style }: { children: ReactNode; style?: object }) {
  return <View style={[s.card, style]}>{children}</View>;
}

export function PrimaryButton({
  label,
  onPress,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={[s.primary, disabled && { opacity: 0.45 }]}
    >
      <Text style={s.primaryText}>{label}</Text>
    </Pressable>
  );
}

export function GhostButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={s.ghost}>
      <Text style={s.ghostText}>{label}</Text>
    </Pressable>
  );
}

export function GField({ label, ...props }: { label: string } & TextInputProps) {
  return (
    <View style={{ marginTop: 14 }}>
      <Text style={s.fieldLabel}>{label}</Text>
      <TextInput placeholderTextColor="#8FA0B1" {...props} style={s.input} />
    </View>
  );
}

export function GBanner({ text, tone = 'danger' }: { text: string; tone?: 'danger' | 'info' }) {
  return (
    <View
      style={[
        s.banner,
        tone === 'danger'
          ? { backgroundColor: light.dangerSoft, borderColor: light.danger }
          : { backgroundColor: light.soft, borderColor: light.line },
      ]}
    >
      <Text style={{ color: tone === 'danger' ? light.danger : light.ink, lineHeight: 20 }}>{text}</Text>
    </View>
  );
}

export function Stepper({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (n: number) => void;
}) {
  return (
    <View style={s.stepRow}>
      <Text style={s.stepLabel}>{label}</Text>
      <View style={s.stepBox}>
        <Pressable
          style={[s.stepBtn, value <= min && { opacity: 0.35 }]}
          disabled={value <= min}
          accessibilityRole="button"
          accessibilityLabel={`Fewer ${label}`}
          onPress={() => onChange(value - 1)}
        >
          <Text style={s.stepText}>−</Text>
        </Pressable>
        <Text style={s.stepValue}>{value}</Text>
        <Pressable
          style={[s.stepBtn, value >= max && { opacity: 0.35 }]}
          disabled={value >= max}
          accessibilityRole="button"
          accessibilityLabel={`More ${label}`}
          onPress={() => onChange(value + 1)}
        >
          <Text style={s.stepText}>+</Text>
        </Pressable>
      </View>
    </View>
  );
}

const DOW = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

/**
 * A month calendar for picking arrival and departure.
 * First tap = arrival, second tap = departure. A tap when both are set starts over.
 */
export function Calendar({
  start,
  end,
  onChange,
  maxNights = 14,
}: {
  start: string | null;
  end: string | null;
  onChange: (start: string | null, end: string | null) => void;
  maxNights?: number;
}) {
  const todayIso = toIso(new Date());
  const [cursor, setCursor] = useState(() => {
    const [y, m] = (start ?? todayIso).split('-').map(Number);
    return { y, m: m - 1 };
  });

  const [ty, tm] = todayIso.split('-').map(Number);
  const atCurrentMonth = cursor.y === ty && cursor.m === tm - 1;

  const lead = (new Date(cursor.y, cursor.m, 1).getDay() + 6) % 7; // weeks start on Monday
  const daysInMonth = new Date(cursor.y, cursor.m + 1, 0).getDate();
  const cells: (string | null)[] = [];
  for (let i = 0; i < lead; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push(`${cursor.y}-${String(cursor.m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`);
  }
  while (cells.length % 7) cells.push(null);

  function step(delta: number) {
    const d = new Date(cursor.y, cursor.m + delta, 1);
    setCursor({ y: d.getFullYear(), m: d.getMonth() });
  }

  function press(iso: string) {
    if (iso < todayIso) return;
    if (!start || end) {
      onChange(iso, null);
      return;
    }
    const nights = nightsBetween(start, iso);
    if (nights < 1 || nights > maxNights) {
      onChange(iso, null);
      return;
    }
    onChange(start, iso);
  }

  return (
    <View>
      <View style={s.calHeader}>
        <Pressable
          onPress={() => step(-1)}
          disabled={atCurrentMonth}
          accessibilityRole="button"
          accessibilityLabel="Previous month"
          style={[s.calNav, atCurrentMonth && { opacity: 0.3 }]}
        >
          <Text style={s.calNavText}>‹</Text>
        </Pressable>
        <Text style={s.calTitle}>
          {MONTHS[cursor.m]} {cursor.y}
        </Text>
        <Pressable
          onPress={() => step(1)}
          accessibilityRole="button"
          accessibilityLabel="Next month"
          style={s.calNav}
        >
          <Text style={s.calNavText}>›</Text>
        </Pressable>
      </View>

      <View style={s.calRow}>
        {DOW.map((d) => (
          <View key={d} style={s.calCell}>
            <Text style={s.calDow}>{d}</Text>
          </View>
        ))}
      </View>

      <View style={s.calGrid}>
        {cells.map((iso, i) => {
          if (!iso) return <View key={`blank-${i}`} style={s.calCell} />;
          const past = iso < todayIso;
          const isStart = iso === start;
          const isEnd = iso === end;
          const inRange = !!start && !!end && iso > start && iso < end;
          return (
            <Pressable
              key={iso}
              onPress={() => press(iso)}
              disabled={past}
              accessibilityRole="button"
              accessibilityLabel={iso}
              style={[s.calCell, inRange && { backgroundColor: light.range }]}
            >
              <View style={[s.calDay, (isStart || isEnd) && { backgroundColor: light.navy }]}>
                <Text
                  style={[
                    s.calDayText,
                    past && { color: '#B7C3CF' },
                    (isStart || isEnd) && { color: '#fff', fontWeight: '700' },
                  ]}
                >
                  {Number(iso.slice(8))}
                </Text>
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: light.bg },
  content: {
    padding: 16,
    paddingTop: 48,
    paddingBottom: 64,
    width: '100%',
    maxWidth: 680,
    alignSelf: 'center',
  },
  wordmark: { fontSize: 24, fontWeight: '800', letterSpacing: 0.5 },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
    minHeight: 36,
  },
  backBtn: { paddingVertical: 6, paddingRight: 12 },
  backText: { color: light.navy, fontSize: 16, fontWeight: '600' },
  card: {
    backgroundColor: light.card,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: light.line,
    padding: 16,
    marginTop: 14,
    overflow: 'hidden',
  },
  primary: {
    backgroundColor: light.amber,
    borderRadius: 14,
    paddingVertical: 15,
    paddingHorizontal: 18,
    alignItems: 'center',
  },
  primaryText: { color: light.onAmber, fontSize: 16, fontWeight: '700' },
  ghost: {
    borderWidth: 1,
    borderColor: light.line,
    backgroundColor: light.card,
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 18,
    alignItems: 'center',
  },
  ghostText: { color: light.navy, fontSize: 15, fontWeight: '600' },
  fieldLabel: { color: light.muted, fontSize: 13, marginBottom: 6, fontWeight: '600' },
  input: {
    backgroundColor: '#fff',
    color: light.ink,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: light.line,
    paddingVertical: 13,
    paddingHorizontal: 14,
    fontSize: 16,
  },
  banner: { borderWidth: 1, borderRadius: 12, padding: 12, marginTop: 14 },
  stepRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
  },
  stepLabel: { color: light.ink, fontSize: 16, fontWeight: '600' },
  stepBox: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  stepBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: light.line,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  stepText: { color: light.navy, fontSize: 22, lineHeight: 24 },
  stepValue: { color: light.ink, fontSize: 18, fontWeight: '700', minWidth: 22, textAlign: 'center' },
  calHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  calNav: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  calNavText: { color: light.navy, fontSize: 26 },
  calTitle: { color: light.ink, fontSize: 16, fontWeight: '700' },
  calRow: { flexDirection: 'row' },
  calGrid: { flexDirection: 'row', flexWrap: 'wrap' },
  calCell: { width: '14.2857%', aspectRatio: 1, alignItems: 'center', justifyContent: 'center' },
  calDow: { color: light.muted, fontSize: 12, fontWeight: '600' },
  calDay: {
    width: '86%',
    aspectRatio: 1,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  calDayText: { color: light.ink, fontSize: 15 },
});
