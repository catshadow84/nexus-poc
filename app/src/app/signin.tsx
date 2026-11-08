import { useState } from 'react';
import { Text, View, TextInput, Pressable, StyleSheet } from 'react-native';
import { router } from 'expo-router';
import { setToken } from '@/lib/session';

export default function SignInScreen() {
  const [value, setValue] = useState('');

  async function save() {
    const token = value.trim();
    if (!token) return;
    await setToken(token);
    router.replace('/');
  }

  return (
    <View style={styles.root}>
      <Text style={styles.brand}>NEXUS</Text>
      <Text style={styles.muted}>Paste your staff key or guest token</Text>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={setValue}
        placeholder="token"
        placeholderTextColor="#667"
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
      />
      <Pressable style={styles.button} onPress={save}>
        <Text style={styles.buttonText}>Continue</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0b0f14', justifyContent: 'center', padding: 24, gap: 16 },
  brand: { color: '#fff', fontSize: 28, fontWeight: '700', letterSpacing: 4 },
  muted: { color: '#8a94a3' },
  input: { backgroundColor: '#161c25', color: '#fff', borderRadius: 10, padding: 14 },
  button: { backgroundColor: '#3b82f6', borderRadius: 10, padding: 14, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '600' },
});