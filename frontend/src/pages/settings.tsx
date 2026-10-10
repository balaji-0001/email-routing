import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, Redirect } from 'wouter';
import { Building2, CircleUserRound, Globe, Inbox, KeyRound, LockKeyhole, MessageSquareText, ScrollText, ShieldCheck, Users } from 'lucide-react';
import { Avatar, Button, EmptyState, Field, PageHeading, SelectField, SkeletonRows, Switch, useToast } from '@/components/kit';
import { navGroups, pageDescriptions, pageTitles } from '@/data';
import { ApiError, api, type Me } from '@/lib/api';
import { dateTime, describeBrowser, localTimezone, shortDate, timeAgo, timezones, titleCase } from '@/lib/format';
import { canManage, useSession } from '@/lib/session';
import { ThemePicker } from '@/lib/theme';
import { AiControls } from './ai';
import { EmailNotificationsPanel } from './collab';
import { AutomationControls } from './automation';
import { PLACEHOLDERS, PlaceholderBody } from './placeholders';

const TABS = navGroups.find((group) => group.title === 'PREFERENCES')!.items.filter(([href]) => href !== '/settings');

function useZones(current: string) {
  // Keep the saved value selectable even if this browser does not list it.
  return useMemo(() => { const zones = timezones(); return zones.includes(current) ? zones : [current, ...zones]; }, [current]);
}

function fieldError(error: unknown, field: string) {
  return error instanceof ApiError ? error.field(field) : undefined;
}

function generalError(error: unknown) {
  if (!error) return null;
  return error instanceof ApiError && !error.details.length ? error.message : error instanceof ApiError ? null : 'Something went wrong. Please try again.';
}

function ProfileForm() {
  const { user, role } = useSession();
  const client = useQueryClient();
  const toast = useToast();
  const [firstName, setFirstName] = useState(user.first_name);
  const [lastName, setLastName] = useState(user.last_name);
  // Someone without a saved time zone sees their browser's, which is saved with their next change.
  const savedTimezone = user.timezone ?? localTimezone();
  const [timezone, setTimezone] = useState(savedTimezone);
  const zones = useZones(timezone);
  const save = useMutation({
    mutationFn: api.updateProfile,
    onSuccess: (updated) => {
      client.setQueryData<Me | null>(['me'], (me) => (me ? { ...me, user: updated } : me));
      client.invalidateQueries({ queryKey: ['members'] });
      toast('Profile saved.');
    },
  });
  const changed = firstName !== user.first_name || lastName !== user.last_name || timezone !== savedTimezone;

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ first_name: firstName, last_name: lastName, timezone });
  }

  return (
    <form className="settings-main panel" onSubmit={submit}>
      <div className="settings-form-head">
        <span className="settings-form-icon"><CircleUserRound size={21} /></span>
        <div><h2>Your profile</h2><p>Personal details used across your workspace.</p></div>
      </div>
      <div className="profile-photo-row">
        <Avatar name={`${firstName} ${lastName}`} className="profile-large" />
        <div><b>{user.name}</b><small>Your initials are shown to teammates. Profile photos aren’t available yet.</small></div>
      </div>
      {generalError(save.error) && <p className="form-error" role="alert">{generalError(save.error)}</p>}
      <div className="form-two">
        <Field label="First name" value={firstName} onChange={setFirstName} error={fieldError(save.error, 'first_name')} autoComplete="given-name" />
        <Field label="Last name" value={lastName} onChange={setLastName} error={fieldError(save.error, 'last_name')} autoComplete="family-name" />
      </div>
      <Field label="Email address" value={user.email} readOnly hint="Changing your email isn’t available yet." />
      <Field label="Role" value={titleCase(role)} readOnly />
      <SelectField label="Time zone" value={timezone} onChange={setTimezone} options={zones} error={fieldError(save.error, 'timezone')} testId="select-timezone" />
      <div className="settings-form-footer">
        <span>{changed ? 'You have unsaved changes.' : 'Everything is saved.'}</span>
        <Button kind="primary" type="submit" disabled={!changed || save.isPending} testId="button-save-profile">{save.isPending ? 'Saving…' : 'Save changes'}</Button>
      </div>
    </form>
  );
}

function WorkspaceForm() {
  const { workspace, role } = useSession();
  const client = useQueryClient();
  const toast = useToast();
  const editable = canManage(role);
  const [name, setName] = useState(workspace.name);
  const [domain, setDomain] = useState(workspace.domain ?? '');
  const [timezone, setTimezone] = useState(workspace.timezone);
  const [invitations, setInvitations] = useState(workspace.allow_invitations);
  const zones = useZones(timezone);
  const save = useMutation({
    mutationFn: api.updateWorkspace,
    onSuccess: (updated) => {
      client.setQueryData<Me | null>(['me'], (me) => (me ? { ...me, workspace: updated } : me));
      client.invalidateQueries({ queryKey: ['audit-events'] });
      toast('Workspace saved.');
    },
  });
  const changed = name !== workspace.name || domain !== (workspace.domain ?? '') || timezone !== workspace.timezone || invitations !== workspace.allow_invitations;

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ name, domain, timezone, allow_invitations: invitations });
  }

  return (
    <form className="settings-main panel" onSubmit={submit}>
      <div className="settings-form-head">
        <span className="settings-form-icon"><Building2 size={21} /></span>
        <div><h2>Workspace identity</h2><p>Created {shortDate(workspace.created_at)}.</p></div>
      </div>
      {!editable && <p className="form-note">Only owners and admins can change these settings.</p>}
      {generalError(save.error) && <p className="form-error" role="alert">{generalError(save.error)}</p>}
      <Field label="Workspace name" value={name} onChange={setName} readOnly={!editable} error={fieldError(save.error, 'name')} />
      <Field label="Workspace domain" value={domain} onChange={setDomain} readOnly={!editable} placeholder="yourcompany.com" error={fieldError(save.error, 'domain')} hint="Optional. Your company’s email domain." />
      <SelectField label="Default time zone" value={timezone} onChange={setTimezone} options={zones} disabled={!editable} error={fieldError(save.error, 'timezone')} testId="select-workspace-timezone" />
      <div className="settings-separator" />
      <div className="settings-control-row">
        <span><b>Allow team invitations</b><small>Saved now and applied once inviting teammates is available.</small></span>
        <Switch on={invitations} onChange={setInvitations} label="Allow team invitations" disabled={!editable} testId="switch-invitations" />
      </div>
      {editable && (
        <div className="settings-form-footer">
          <span>{changed ? 'You have unsaved changes.' : 'Everything is saved.'}</span>
          <Button kind="primary" type="submit" disabled={!changed || save.isPending} testId="button-save-workspace">{save.isPending ? 'Saving…' : 'Save changes'}</Button>
        </div>
      )}
    </form>
  );
}

function PasswordSection() {
  const { user } = useSession();
  const client = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const change = useMutation({
    mutationFn: api.changePassword,
    onSuccess: () => {
      setOpen(false);
      setCurrent('');
      setNext('');
      client.invalidateQueries({ queryKey: ['me'] });
      client.invalidateQueries({ queryKey: ['sessions'] });
      toast('Password changed. Other browsers were signed out.');
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    change.mutate({ current_password: current, new_password: next });
  }

  return (
    <>
      <div className="security-row">
        <span className="security-icon"><KeyRound size={18} /></span>
        <div><b>Password</b><small>Last changed {shortDate(user.password_changed_at)}</small></div>
        {!open && <Button onClick={() => setOpen(true)} testId="button-change-password">Change password</Button>}
      </div>
      {open && (
        <form className="security-form" onSubmit={submit}>
          {generalError(change.error) && <p className="form-error" role="alert">{generalError(change.error)}</p>}
          <div className="form-two">
            <Field label="Current password" value={current} onChange={setCurrent} type="password" error={fieldError(change.error, 'current_password')} autoComplete="current-password" />
            <Field label="New password" value={next} onChange={setNext} type="password" error={fieldError(change.error, 'new_password')} hint="At least 8 characters." autoComplete="new-password" />
          </div>
          <div className="security-form-actions">
            <Button onClick={() => { setOpen(false); change.reset(); }}>Cancel</Button>
            <Button kind="primary" type="submit" disabled={!current || next.length < 8 || change.isPending} testId="button-save-password">{change.isPending ? 'Saving…' : 'Save password'}</Button>
          </div>
        </form>
      )}
    </>
  );
}

function SessionsSection() {
  const client = useQueryClient();
  const toast = useToast();
  const sessions = useQuery({ queryKey: ['sessions'], queryFn: api.sessions });
  const revoke = useMutation({
    mutationFn: api.revokeOtherSessions,
    onSuccess: ({ ended }) => {
      client.invalidateQueries({ queryKey: ['sessions'] });
      toast(ended === 1 ? 'Signed out of 1 other session.' : `Signed out of ${ended} other sessions.`);
    },
  });
  const others = sessions.data?.filter((session) => !session.current).length ?? 0;

  return (
    <>
      <div className="security-row">
        <span className="security-icon"><Globe size={18} /></span>
        <div><b>Where you’re signed in</b><small>{sessions.isLoading ? 'Loading…' : others ? `This browser and ${others} other${others === 1 ? '' : 's'}` : 'Only this browser'}</small></div>
        {others > 0 && <Button onClick={() => revoke.mutate()} disabled={revoke.isPending} testId="button-revoke-sessions">Sign out the others</Button>}
      </div>
      {sessions.data?.map((session) => (
        <div className="session-row" key={session.id} data-testid="row-session">
          <span><b>{describeBrowser(session.user_agent)}</b>{session.current && <em className="you-tag">This browser</em>}</span>
          <small>{session.ip_address ?? 'Unknown address'} · signed in {dateTime(session.created_at)} · last used {timeAgo(session.last_used_at)}</small>
        </div>
      ))}
    </>
  );
}

function SecurityPanel() {
  return (
    <div className="settings-main panel">
      <div className="settings-form-head">
        <span className="settings-form-icon"><LockKeyhole size={21} /></span>
        <div><h2>Sign-in & security</h2><p>Keep your account protected.</p></div>
      </div>
      <PasswordSection />
      <SessionsSection />
      <div className="security-row">
        <span className="security-icon"><ShieldCheck size={18} /></span>
        <div><b>Two-factor authentication</b><small>A second step when signing in.</small></div>
        <span className="disabled-label">Not available yet</span>
      </div>
    </div>
  );
}

function UsagePanel() {
  const members = useQuery({ queryKey: ['members'], queryFn: api.members });
  return (
    <>
      <div className="assignment-summary">
        <div className="panel assignment-stat"><span><Users size={16} /> Team members</span><b data-testid="stat-members">{members.data?.length ?? '–'}</b><small>People who can sign in</small></div>
        <div className="panel assignment-stat"><span><Inbox size={16} /> Connected inboxes</span><b>0</b><small>None connected yet</small></div>
        <div className="panel assignment-stat"><span><MessageSquareText size={16} /> Conversations</span><b>0</b><small>No mail yet</small></div>
      </div>
      <p className="form-note">Plans and limits aren’t set up yet, so nothing is capped.</p>
    </>
  );
}

function AuditPanel() {
  const { role } = useSession();
  const allowed = canManage(role);
  const events = useQuery({ queryKey: ['audit-events', 100], queryFn: () => api.auditEvents(100), enabled: allowed });

  if (!allowed) return <EmptyState icon={ScrollText} title="Only owners and admins can read the audit log">Ask a workspace owner if you need to check what changed.</EmptyState>;

  return (
    <section className="panel table-panel">
      <div className="table-toolbar"><div><b>Workspace activity</b><span>{events.data ? `Latest ${events.data.length} ${events.data.length === 1 ? 'event' : 'events'}` : 'Loading…'}</span></div></div>
      {events.isLoading ? (
        <SkeletonRows rows={4} />
      ) : events.isError ? (
        <EmptyState bare icon={ScrollText} title="We couldn’t load the audit log">Refresh the page to try again.</EmptyState>
      ) : !events.data?.length ? (
        <EmptyState bare icon={ScrollText} title="Nothing recorded yet">Sign-ins and changes to this workspace are listed here as they happen.</EmptyState>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table audit-table">
            <thead><tr><th>Who</th><th>What</th><th>When</th><th>From</th></tr></thead>
            <tbody>
              {events.data.map((event) => (
                <tr key={event.id} data-testid="row-audit">
                  <td><div className="table-person"><Avatar name={event.actor_name ?? '?'} /><b>{event.actor_name ?? 'Removed user'}{event.actor_is_you && <em className="you-tag">You</em>}</b></div></td>
                  <td>{event.summary}</td>
                  <td title={new Date(event.created_at).toLocaleString()}>{dateTime(event.created_at)}</td>
                  <td>{event.ip_address ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function SettingsPage({ path }: { path: string }) {
  // Each tab starts at the top of the page.
  useEffect(() => { window.scrollTo({ top: 0 }); }, [path]);
  if (path === '/settings') return <Redirect to="/settings/profile" replace />;

  return (
    <>
      <PageHeading eyebrow="PREFERENCES" title={pageTitles[path]} description={pageDescriptions[path]} />
      <div className="settings-tabs">
        {TABS.map(([href, label]) => <Link className={href === path ? 'selected' : ''} href={href} key={href}>{label}</Link>)}
      </div>
      {path === '/settings/profile' && (
        <section className="panel settings-main appearance-panel" data-testid="panel-appearance">
          <div><h2>Appearance</h2><p>How the app looks in this browser. “Custom” is the glass design.</p></div>
          <ThemePicker />
        </section>
      )}
      {path === '/settings/profile' && <EmailNotificationsPanel />}
      {path === '/settings/profile' ? <ProfileForm key="profile" />
        : path === '/settings/workspace' ? <WorkspaceForm key="workspace" />
        : path === '/settings/security' ? <SecurityPanel />
        : path === '/settings/usage' ? <UsagePanel />
        : path === '/settings/audit-logs' ? <AuditPanel />
        : path === '/settings/automation' ? <AutomationControls />
        : path === '/settings/ai' ? <AiControls />
        : PLACEHOLDERS[path] ? <PlaceholderBody path={path} />
        : null}
    </>
  );
}
