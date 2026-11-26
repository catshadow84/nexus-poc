import { Stack } from 'expo-router';

import '@/lib/web-alert';

export default function RootLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}