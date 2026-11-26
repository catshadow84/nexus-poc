import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { light } from '@/lib/brand';
import { allPhotos } from '@/lib/rooms';
import { markWelcomeSeen } from '@/lib/session';
import { PrimaryButton, Wordmark } from '@/components/guest-ui';

const SLIDES = [
  {
    title: 'Find your room',
    text: 'Pick your dates and see what is free right now. No calls, no waiting.',
  },
  {
    title: 'No lines, no key card',
    text: 'Book on your phone and unlock your door from the same app.',
  },
  {
    title: 'Your room, your way',
    text: 'Lights, air conditioning, music and a concierge, all in one place.',
  },
];

export default function WelcomeScreen() {
  const [index, setIndex] = useState(0);
  const slide = SLIDES[index];
  const last = index === SLIDES.length - 1;

  async function finish() {
    await markWelcomeSeen();
    router.replace('/search');
  }

  return (
    <View style={styles.root}>
      <View style={styles.column}>
        <Image source={allPhotos[index]} style={styles.photo} resizeMode="cover" />
        <View style={styles.badge}>
          <Wordmark color="#fff" />
        </View>

        <View style={styles.body}>
          <Text style={styles.title}>{slide.title}</Text>
          <Text style={styles.text}>{slide.text}</Text>

          <View style={styles.dots}>
            {SLIDES.map((_, i) => (
              <View key={i} style={[styles.dot, i === index && styles.dotOn]} />
            ))}
          </View>

          <PrimaryButton
            label={last ? 'Get started' : 'Next'}
            onPress={() => (last ? finish() : setIndex(index + 1))}
          />
          {!last && (
            <Pressable onPress={finish} accessibilityRole="button" style={styles.skip}>
              <Text style={styles.skipText}>Skip</Text>
            </Pressable>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: light.bg },
  column: { flex: 1, width: '100%', maxWidth: 520, alignSelf: 'center', backgroundColor: light.bg },
  photo: { width: '100%', height: '52%' },
  badge: {
    position: 'absolute',
    top: 48,
    left: 20,
    backgroundColor: 'rgba(15,35,56,0.55)',
    borderRadius: 12,
    paddingVertical: 4,
    paddingHorizontal: 12,
  },
  body: {
    flex: 1,
    marginTop: -24,
    backgroundColor: light.bg,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    padding: 24,
    justifyContent: 'center',
  },
  title: { color: light.ink, fontSize: 28, fontWeight: '800' },
  text: { color: light.muted, fontSize: 16, lineHeight: 24, marginTop: 8 },
  dots: { flexDirection: 'row', gap: 8, marginVertical: 22 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: light.line },
  dotOn: { width: 24, backgroundColor: light.navy },
  skip: { alignSelf: 'center', paddingVertical: 14, paddingHorizontal: 20 },
  skipText: { color: light.muted, fontSize: 15, fontWeight: '600' },
});
