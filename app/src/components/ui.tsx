import { ReactNode } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
} from 'react-native';
import { brand } from '@/lib/brand';

/** "5 min ago" for a time the server sent (naive UTC, no Z at the end). */
export function ago(iso?: string | null): string {
  if (!iso) return '';
  const time = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z').getTime();
  const minutes = Math.round((Date.now() - time) / 60000);
  if (Number.isNaN(minutes)) return '';
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function roomLabel(roomId: string): string {
  return roomId.replace(/^room\s*/i, 'Room ');
}

/** A scrolling page, centered and no wider than 760 px so it also looks right in a browser. */
export function Screen({ children }: { children: ReactNode }) {
  return (
    <View style={s.root}>
      <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
    </View>
  );
}

export function Header({
  title,
  subtitle,
  onBack,
}: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
}) {
  return (
    <View style={s.header}>
      <Text style={s.wordmark}>
        nexus<Text style={{ color: brand.amber }}>.</Text>
      </Text>
      {onBack && (
        <Pressable onPress={onBack} style={s.back} accessibilityRole="button">
          <Text style={s.backText}>‹ Back</Text>
        </Pressable>
      )}
      <Text style={s.title}>{title}</Text>
      {subtitle ? <Text style={s.subtitle}>{subtitle}</Text> : null}
    </View>
  );
}

export function Card({ children }: { children: ReactNode }) {
  return <View style={s.card}>{children}</View>;
}

type ButtonKind = 'primary' | 'ghost' | 'danger';

export function Button({
  label,
  onPress,
  kind = 'primary',
  small = false,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  kind?: ButtonKind;
  small?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={[
        s.button,
        small && s.buttonSmall,
        kind === 'primary' && s.buttonPrimary,
        kind === 'ghost' && s.buttonGhost,
        kind === 'danger' && s.buttonDanger,
        disabled && { opacity: 0.5 },
      ]}
    >
      <Text
        style={[
          s.buttonText,
          small && { fontSize: 13 },
          kind === 'primary' && { color: brand.onAmber },
          kind === 'danger' && { color: brand.danger },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

type Tone = 'neutral' | 'ok' | 'warn' | 'danger' | 'info';
const toneColor: Record<Tone, string> = {
  neutral: brand.muted,
  ok: brand.ok,
  warn: brand.warn,
  danger: brand.danger,
  info: brand.info,
};

export function Chip({
  label,
  tone = 'neutral',
  selected = false,
  onPress,
}: {
  label: string;
  tone?: Tone;
  selected?: boolean;
  onPress?: () => void;
}) {
  const color = toneColor[tone];
  const body = (
    <View
      style={[
        s.chip,
        { borderColor: color },
        selected && { backgroundColor: color },
      ]}
    >
      <Text style={[s.chipText, { color: selected ? brand.onAmber : color }]}>{label}</Text>
    </View>
  );
  return onPress ? (
    <Pressable onPress={onPress} accessibilityRole="button">
      {body}
    </Pressable>
  ) : (
    body
  );
}

export function Field({ label, ...props }: { label: string } & TextInputProps) {
  return (
    <View style={{ marginTop: 12 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput
        placeholderTextColor={brand.muted}
        {...props}
        style={[s.input, props.multiline && { minHeight: 80, textAlignVertical: 'top' }]}
      />
    </View>
  );
}

export function Banner({ text, tone = 'danger' }: { text: string; tone?: Tone }) {
  return (
    <View style={[s.banner, { borderColor: toneColor[tone] }]}>
      <Text style={{ color: toneColor[tone] }}>{text}</Text>
    </View>
  );
}

export const text = StyleSheet.create({
  strong: { color: brand.text, fontSize: 17, fontWeight: '600' },
  muted: { color: brand.muted, marginTop: 4, lineHeight: 20 },
});

export const layout = StyleSheet.create({
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  rowSpread: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  gap: { marginTop: 12 },
});

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: brand.bg },
  content: {
    padding: 20,
    paddingTop: 56,
    paddingBottom: 64,
    width: '100%',
    maxWidth: 760,
    alignSelf: 'center',
  },
  header: { marginBottom: 20 },
  wordmark: { color: brand.text, fontSize: 22, fontWeight: '800', letterSpacing: 1 },
  back: { paddingVertical: 8, alignSelf: 'flex-start' },
  backText: { color: brand.muted, fontSize: 15 },
  title: { color: brand.text, fontSize: 28, fontWeight: '700', marginTop: 8 },
  subtitle: { color: brand.muted, marginTop: 4, fontSize: 15 },
  card: {
    backgroundColor: brand.surface,
    borderRadius: 16,
    padding: 16,
    marginTop: 12,
    borderWidth: 1,
    borderColor: brand.border,
  },
  button: {
    borderRadius: 12,
    paddingVertical: 13,
    paddingHorizontal: 18,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'transparent',
  },
  buttonSmall: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10 },
  buttonPrimary: { backgroundColor: brand.amber },
  buttonGhost: { borderColor: brand.border, backgroundColor: brand.surfaceSoft },
  buttonDanger: { borderColor: brand.danger },
  buttonText: { color: brand.text, fontWeight: '600', fontSize: 15 },
  chip: {
    borderWidth: 1,
    borderRadius: 999,
    paddingVertical: 4,
    paddingHorizontal: 10,
  },
  chipText: { fontSize: 12, fontWeight: '600' },
  label: { color: brand.muted, fontSize: 12, letterSpacing: 0.5, marginBottom: 6 },
  input: {
    backgroundColor: brand.surfaceSoft,
    color: brand.text,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: brand.border,
    paddingVertical: 12,
    paddingHorizontal: 14,
    fontSize: 16,
  },
  banner: { borderWidth: 1, borderRadius: 12, padding: 12, marginTop: 12 },
});