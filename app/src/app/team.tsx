import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { api } from '@/lib/api';
import { brand, ROLE_LABEL } from '@/lib/brand';
import { type StaffRole } from '@/lib/session';
import { Banner, Button, Card, Chip, Field, Header, Screen, layout, text } from '@/components/ui';

type Account = {
  id: string;
  username: string;
  name: string;
  role: StaffRole;
  active: boolean;
};

const ROLES: StaffRole[] = ['front_desk', 'housekeeping', 'maintenance', 'manager'];

export default function TeamScreen() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState<StaffRole>('front_desk');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setAccounts(await api<Account[]>('/staff/accounts'));
      setError(null);
    } catch (e: any) {
      if (e.status === 401) {
        router.replace('/signin');
        return;
      }
      setError(e.status === 403 ? 'Only managers can manage the team.' : (e.message ?? 'Could not load the team'));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await api('/staff/accounts', {
        method: 'POST',
        body: { username: username.trim(), name: name.trim(), role, password },
      });
      setUsername('');
      setName('');
      setPassword('');
      setFormOpen(false);
      await load();
    } catch (e: any) {
      setError(e.message ?? 'Could not create the account');
    } finally {
      setBusy(false);
    }
  }

  async function setActive(account: Account, active: boolean) {
    setError(null);
    try {
      await api(`/staff/accounts/${account.id}`, { method: 'PATCH', body: { active } });
      await load();
    } catch (e: any) {
      setError(e.message ?? 'Could not change the account');
    }
  }

  return (
    <Screen>
      <Header
        title="Team"
        subtitle="Create accounts and choose what each person can do."
        onBack={() => router.replace('/staff-home')}
      />

      <View style={layout.row}>
        <Button
          small
          label={formOpen ? 'Close form' : 'Add a person'}
          kind={formOpen ? 'ghost' : 'primary'}
          onPress={() => setFormOpen(!formOpen)}
        />
      </View>

      {formOpen && (
        <Card>
          <Field label="Full name" value={name} onChangeText={setName} autoComplete="name" />
          <Field
            label="Username (letters and digits, no spaces)"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <View style={{ marginTop: 12 }}>
            <Text style={{ color: brand.muted, fontSize: 12, marginBottom: 6 }}>Role</Text>
            <View style={layout.row}>
              {ROLES.map((r) => (
                <Chip key={r} label={ROLE_LABEL[r]} selected={role === r} onPress={() => setRole(r)} />
              ))}
            </View>
          </View>
          <Field
            label="Password (at least 10 characters)"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoCapitalize="none"
          />
          <View style={layout.gap}>
            <Button label={busy ? 'Creating…' : 'Create account'} onPress={create} disabled={busy} />
          </View>
        </Card>
      )}

      {error && <Banner text={error} />}
      {!accounts && !error && <Text style={{ color: brand.muted, marginTop: 16 }}>Loading team…</Text>}

      {accounts?.map((account) => (
        <Card key={account.id}>
          <View style={layout.rowSpread}>
            <Text style={[text.strong, { flex: 1 }]}>{account.name}</Text>
            <Chip label={ROLE_LABEL[account.role]} tone="info" />
          </View>
          <Text style={text.muted}>
            @{account.username} · {account.active ? 'Active' : 'Deactivated'}
          </Text>
          <View style={[layout.row, layout.gap]}>
            {account.active ? (
              <Button small kind="danger" label="Deactivate" onPress={() => setActive(account, false)} />
            ) : (
              <Button small kind="ghost" label="Reactivate" onPress={() => setActive(account, true)} />
            )}
          </View>
        </Card>
      ))}
    </Screen>
  );
}