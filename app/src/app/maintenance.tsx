import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { api } from '@/lib/api';
import { brand } from '@/lib/brand';
import { getStaff, type StaffRole } from '@/lib/session';
import { Banner, Button, Card, Chip, Field, Header, Screen, ago, layout, roomLabel, text } from '@/components/ui';

type IssueStatus = 'open' | 'in_progress' | 'resolved';
type Issue = {
  id: string;
  room_id: string;
  title: string;
  details: string;
  status: IssueStatus;
  reported_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
};

const LABEL: Record<IssueStatus, string> = { open: 'Open', in_progress: 'In progress', resolved: 'Resolved' };
const TONE: Record<IssueStatus, 'danger' | 'warn' | 'ok'> = { open: 'danger', in_progress: 'warn', resolved: 'ok' };
const NEXT: Record<IssueStatus, { status: IssueStatus; label: string }[]> = {
  open: [
    { status: 'in_progress', label: 'Start work' },
    { status: 'resolved', label: 'Resolve' },
  ],
  in_progress: [
    { status: 'resolved', label: 'Resolve' },
    { status: 'open', label: 'Back to open' },
  ],
  resolved: [{ status: 'open', label: 'Reopen' }],
};

export default function MaintenanceScreen() {
  const { room_id } = useLocalSearchParams<{ room_id?: string }>();
  const [issues, setIssues] = useState<Issue[] | null>(null);
  const [role, setRole] = useState<StaffRole | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [formOpen, setFormOpen] = useState(Boolean(room_id));
  const [room, setRoom] = useState(room_id ?? '');
  const [title, setTitle] = useState('');
  const [details, setDetails] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setIssues(await api<Issue[]>(`/maintenance/issues?status=${showAll ? 'all' : 'unresolved'}`));
      setError(null);
    } catch (e: any) {
      if (e.status === 401) {
        router.replace('/signin');
        return;
      }
      setError(e.status === 403 ? 'Your role cannot see this screen.' : (e.message ?? 'Could not load issues'));
    }
  }, [showAll]);

  useFocusEffect(
    useCallback(() => {
      getStaff().then((s) => setRole(s?.role ?? null));
      load();
      const timer = setInterval(load, 15000);
      return () => clearInterval(timer);
    }, [load]),
  );

  async function report() {
    if (!room.trim()) {
      setError('Which room? For example room3.');
      return;
    }
    if (title.trim().length < 3) {
      setError('Give the problem a short title (at least 3 characters).');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api('/maintenance/issues', {
        method: 'POST',
        body: { room_id: room.trim().toLowerCase().replace(/\s+/g, ''), title: title.trim(), details: details.trim() },
      });
      setTitle('');
      setDetails('');
      setFormOpen(false);
      await load();
    } catch (e: any) {
      setError(e.message ?? 'Could not report the issue');
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(issue: Issue, status: IssueStatus) {
    setError(null);
    try {
      await api(`/maintenance/issues/${issue.id}`, { method: 'PATCH', body: { status } });
      await load();
    } catch (e: any) {
      setError(e.message ?? 'Could not change the issue');
    }
  }

  const canManage = role === 'maintenance' || role === 'front_desk' || role === 'manager';

  return (
    <Screen>
      <Header
        title="Maintenance"
        subtitle="Report a problem, or work through the list."
        onBack={() => router.replace('/staff-home')}
      />

      <View style={layout.row}>
        <Button
          small
          label={formOpen ? 'Close form' : 'Report an issue'}
          kind={formOpen ? 'ghost' : 'primary'}
          onPress={() => setFormOpen(!formOpen)}
        />
        <Chip label="Unresolved" selected={!showAll} onPress={() => setShowAll(false)} />
        <Chip label="All" selected={showAll} onPress={() => setShowAll(true)} />
      </View>

      {formOpen && (
        <Card>
          <Field label="Room" value={room} onChangeText={setRoom} placeholder="room3" autoCapitalize="none" />
          <Field label="What is wrong?" value={title} onChangeText={setTitle} placeholder="Shower drain blocked" />
          <Field label="Details (optional)" value={details} onChangeText={setDetails} multiline />
          <View style={layout.gap}>
            <Button label={busy ? 'Sending…' : 'Send report'} onPress={report} disabled={busy} />
          </View>
        </Card>
      )}

      {error && <Banner text={error} />}
      {!issues && !error && <Text style={{ color: brand.muted, marginTop: 16 }}>Loading issues…</Text>}
      {issues && issues.length === 0 && (
        <Text style={{ color: brand.muted, marginTop: 16 }}>
          {showAll ? 'No issues yet.' : 'No open issues. Nice.'}
        </Text>
      )}

      {issues?.map((issue) => (
        <Card key={issue.id}>
          <View style={layout.rowSpread}>
            <Text style={[text.strong, { flex: 1 }]}>{issue.title}</Text>
            <Chip label={LABEL[issue.status]} tone={TONE[issue.status]} selected />
          </View>
          <Text style={text.muted}>
            {roomLabel(issue.room_id)} · reported {ago(issue.created_at)}
            {issue.reported_by ? ` by ${issue.reported_by}` : ''}
          </Text>
          {issue.details ? <Text style={text.muted}>{issue.details}</Text> : null}
          {issue.status !== 'open' && issue.updated_by && (
            <Text style={text.muted}>
              Last update {ago(issue.updated_at)} by {issue.updated_by}
            </Text>
          )}
          {canManage && (
            <View style={[layout.row, layout.gap]}>
              {NEXT[issue.status].map((next) => (
                <Button
                  key={next.status}
                  small
                  kind={next.status === 'resolved' ? 'primary' : 'ghost'}
                  label={next.label}
                  onPress={() => changeStatus(issue, next.status)}
                />
              ))}
            </View>
          )}
        </Card>
      ))}
    </Screen>
  );
}