import { useState } from 'react';
import { Text, View } from 'react-native';
import { router } from 'expo-router';
import { api } from '@/lib/api';
import { brand } from '@/lib/brand';
import { clearStaff, setStaff, setToken, type StaffRole } from '@/lib/session';
import { Banner, Button, Card, Field, Header, Screen, layout } from '@/components/ui';

type LoginResponse = { token: string; role: StaffRole; name: string; username: string };

export default function SignInScreen() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [pasted, setPasted] = useState('');

  async function signIn() {
    if (!username.trim() || !password) {
      setError('Enter your username and password.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api<LoginResponse>('/staff/login', {
        method: 'POST',
        body: { username: username.trim(), password },
      });
      await setToken(res.token);
      await setStaff({ role: res.role, name: res.name, username: res.username });
      router.replace('/staff-home');
    } catch (e: any) {
      setError(e.message ?? 'Could not sign in.');
    } finally {
      setBusy(false);
    }
  }

  async function usePastedToken() {
    const token = pasted.trim();
    if (!token) return;
    await clearStaff();
    await setToken(token);
    router.replace('/');
  }

  return (
    <Screen>
      <Header title="Staff sign in" subtitle="Use the account your manager created for you." />
      <Card>
        <Field
          label="Username"
          value={username}
          onChangeText={setUsername}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="username"
        />
        <Field
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          autoComplete="current-password"
          returnKeyType="go"
          onSubmitEditing={signIn}
        />
        {error && <Banner text={error} />}
        <View style={layout.gap}>
          <Button label={busy ? 'Signing in…' : 'Sign in'} onPress={signIn} disabled={busy} />
        </View>
      </Card>

      <View style={[layout.gap, { alignItems: 'center', gap: 12 }]}>
        <Button label="I'm a guest: find a stay" kind="ghost" onPress={() => router.push('/search')} />
        <Text style={{ color: brand.muted }} onPress={() => setAdvanced(!advanced)}>
          {advanced ? 'Hide advanced' : 'Advanced: use a token'}
        </Text>
      </View>

      {advanced && (
        <Card>
          <Field
            label="Staff key or guest token"
            value={pasted}
            onChangeText={setPasted}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
          />
          <View style={layout.gap}>
            <Button label="Continue with token" kind="ghost" onPress={usePastedToken} />
          </View>
        </Card>
      )}
    </Screen>
  );
}