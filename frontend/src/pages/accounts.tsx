import { Fragment, useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useSearch } from 'wouter';
import { AlertTriangle, ArrowLeft, Check, Copy, ShieldCheck, UserPlus, Users, CheckCircle2, Info, Mail, Plus, RefreshCw, Unlink } from 'lucide-react';
import { Button, EmptyState, Field, PageHeading, SkeletonRows, useToast } from '@/components/kit';
import { pageDescriptions } from '@/data';
import { api, ApiError, type ConnectAccountData, type EmailAccount, type MailboxAccessMember, type MailboxPermission, type Role } from '@/lib/api';
import { timeAgo, titleCase } from '@/lib/format';
import { canManage, useSession } from '@/lib/session';

/** Why a return from Google did not connect a mailbox, in the user's words. */
const GMAIL_ERRORS: Record<string, string> = {
  denied: 'Google sign-in was cancelled, so nothing was connected.',
  missing_permission: 'The mailbox was not connected because permission to read or send mail was not given. Try again and leave both boxes ticked on Google’s screen.',
  expired: 'That sign-in attempt is no longer valid. Start again from “Sign in with Google”.',
  signed_out: 'You were signed out before Google finished. Sign in and connect the mailbox again.',
  forbidden: 'Only workspace owners and admins can connect email accounts.',
  not_configured: 'Connecting with Google isn’t set up on this server yet.',
  failed: 'Google could not complete the connection. Try again in a moment.',
};

/** Sends the browser to Google to approve access; Google sends it back to the Email accounts page. */
function useGoogleConnect() {
  const toast = useToast();
  return useMutation({
    mutationFn: api.startGoogleConnect,
    onSuccess: ({ authorization_url }) => window.location.assign(authorization_url),
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not start Google sign-in.'),
  });
}

export function AccountsPage() {
  const { role } = useSession();
  const client = useQueryClient();
  const toast = useToast();
  const isManager = canManage(role);
  const [, navigate] = useLocation();
  const search = useSearch();
  const [gmailError, setGmailError] = useState<string | null>(null);
  const [accessFor, setAccessFor] = useState<number | null>(null);
  const googleConnect = useGoogleConnect();

  // Coming back from Google: say what happened once, then tidy the address bar.
  useEffect(() => {
    const params = new URLSearchParams(search);
    const connected = params.get('gmail_connected');
    const failed = params.get('gmail_error');
    if (!connected && !failed) return;
    if (connected) {
      toast(`Connected ${connected}. Its mail is being imported.`);
      client.invalidateQueries({ queryKey: ['email-accounts'] });
      client.invalidateQueries({ queryKey: ['conversations'] });
    }
    if (failed) setGmailError(GMAIL_ERRORS[failed] ?? GMAIL_ERRORS.failed);
    navigate('/accounts', { replace: true });
  }, [search]); // eslint-disable-line react-hooks/exhaustive-deps

  const accounts = useQuery({
    queryKey: ['email-accounts'],
    queryFn: api.emailAccounts,
    // While older mail is still coming in, keep the count moving.
    refetchInterval: (query) => (query.state.data?.some((acc) => acc.import_state !== 'done') ? 5000 : false),
  });

  const syncAccount = useMutation({
    mutationFn: (id: number) => api.syncEmailAccount(id),
    onSuccess: (res) => {
      client.invalidateQueries({ queryKey: ['email-accounts'] });
      client.invalidateQueries({ queryKey: ['conversations'] });
      if (res.error) {
        toast(`Sync error: ${res.error}`);
      } else {
        toast(`Synced ${res.synced_messages} message${res.synced_messages === 1 ? '' : 's'}.`);
      }
    },
    onError: (err) => {
      toast(err instanceof ApiError ? err.message : 'Could not sync account.');
    },
  });

  const disconnectAccount = useMutation({
    mutationFn: (id: number) => api.disconnectEmailAccount(id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['email-accounts'] });
      client.invalidateQueries({ queryKey: ['conversations'] });
      toast('Email account disconnected.');
    },
    onError: (err) => {
      toast(err instanceof ApiError ? err.message : 'Could not disconnect account.');
    },
  });

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <PageHeading eyebrow="CONNECTED" title="Email accounts" description={pageDescriptions['/accounts']} />
        {isManager && (
          <Link href="/accounts/add" className="auth-submit" style={{ textDecoration: 'none', padding: '0.6rem 1.2rem', fontSize: '0.9rem', width: 'auto' }}>
            <Plus size={18} /> Add account
          </Link>
        )}
      </div>

      {gmailError && (
        <div className="auth-notice auth-notice-error" style={{ marginTop: '1rem' }} role="alert" data-testid="notice-gmail-error">
          <AlertTriangle size={18} />
          <span>{gmailError}</span>
        </div>
      )}

      <section className="panel table-panel" style={{ marginTop: '1rem' }}>
        <div className="table-toolbar">
          <div><b>Connected inboxes</b><span>{accounts.data ? `${accounts.data.length} accounts` : 'Loading…'}</span></div>
        </div>

        {accounts.isLoading ? (
          <SkeletonRows rows={2} />
        ) : !accounts.data?.length ? (
          <EmptyState icon={Mail} title="No email accounts connected yet">
            Connect a Gmail, Microsoft 365, or IMAP/SMTP inbox so your team can read and answer customer emails in one shared space.
            {isManager && (
              <div style={{ marginTop: '1rem' }}>
                <Link href="/accounts/add" className="auth-submit" style={{ display: 'inline-flex', width: 'auto', textDecoration: 'none' }}>
                  <Plus size={18} /> Connect your first account
                </Link>
              </div>
            )}
          </EmptyState>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table accounts-table">
              <thead><tr><th>Account</th><th>Provider</th><th>Status</th><th>Last synced</th><th>Messages</th><th>Who can use it</th><th>Actions</th></tr></thead>
              <tbody>
                {accounts.data.map((acc) => (
                  <Fragment key={acc.id}>
                  <tr>
                    <td>
                      <div className="table-person">
                        <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'rgba(255,255,255,0.1)', display: 'grid', placeItems: 'center' }}>
                          <Mail size={18} />
                        </div>
                        <span><b>{acc.display_name || acc.email_address}</b><small>{acc.email_address}</small></span>
                      </div>
                    </td>
                    <td><span className="role-pill">{acc.provider === 'gmail' ? (acc.auth_type === 'oauth' ? 'Gmail' : 'Gmail (app password)') : acc.provider.toUpperCase()}</span></td>
                    <td>
                      {acc.status === 'connected' ? (
                        <span style={{ color: 'var(--status-ok)', display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.85rem' }}>
                          <CheckCircle2 size={15} /> Connected
                        </span>
                      ) : acc.status === 'syncing' ? (
                        <span style={{ color: 'var(--status-info)', display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.85rem' }}>
                          <RefreshCw size={15} className="ns-spin" /> Syncing…
                        </span>
                      ) : acc.status === 'needs_reconnect' ? (
                        <span style={{ color: 'var(--status-warn)', display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.85rem' }} title={acc.last_error ?? ''} data-testid={`status-needs-reconnect-${acc.id}`}>
                          <AlertTriangle size={15} /> Needs reconnecting
                        </span>
                      ) : (
                        <span style={{ color: 'var(--status-bad)', display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.85rem' }} title={acc.last_error ?? ''}>
                          Error
                        </span>
                      )}
                    </td>
                    <td>{acc.last_sync_at ? titleCase(timeAgo(acc.last_sync_at)) : 'Never'}</td>
                    <td>
                      <b>{acc.message_count.toLocaleString()}</b>
                      {acc.import_state !== 'done' && (
                        <small style={{ display: 'block', opacity: 0.8 }} data-testid={`text-import-progress-${acc.id}`}>
                          Importing older mail{acc.import_total ? ` (about ${acc.import_total.toLocaleString()} in the inbox)` : ''}…
                        </small>
                      )}
                    </td>
                    <td>
                      <span className="role-pill" data-testid={`text-access-${acc.id}`}>
                        {acc.access_mode === 'restricted' ? <><ShieldCheck size={14} /> Chosen roles</> : <><Users size={14} /> Everyone</>}
                      </span>
                      {!isManager && acc.my_permission === 'read' && <small style={{ display: 'block', opacity: 0.8 }}>You can read, not send</small>}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        {isManager && (
                          <Button kind="secondary" onClick={() => setAccessFor(accessFor === acc.id ? null : acc.id)} testId={`button-access-${acc.id}`}>
                            <ShieldCheck size={14} /> Access
                          </Button>
                        )}
                        {isManager && acc.auth_type === 'oauth' && acc.status === 'needs_reconnect' && (
                          <Button kind="primary" onClick={() => googleConnect.mutate()} disabled={googleConnect.isPending} testId={`button-reconnect-${acc.id}`}>
                            {googleConnect.isPending ? 'Opening Google…' : 'Reconnect'}
                          </Button>
                        )}
                        <Button
                          kind="secondary"
                          onClick={() => syncAccount.mutate(acc.id)}
                          disabled={syncAccount.isPending}
                        >
                          <RefreshCw size={14} className={syncAccount.isPending ? 'ns-spin' : ''} /> Sync
                        </Button>
                        {isManager && (
                          <Button
                            kind="secondary"
                            onClick={() => {
                              if (confirm(`Disconnect and remove ${acc.email_address}? Synced messages will remain.`)) {
                                disconnectAccount.mutate(acc.id);
                              }
                            }}
                            disabled={disconnectAccount.isPending}
                          >
                            <Unlink size={14} /> Disconnect
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {accessFor === acc.id && (
                    <tr className="access-row"><td colSpan={7}><AccessPanel account={acc} onClose={() => setAccessFor(null)} /></td></tr>
                  )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

type Level = MailboxPermission | 'none';

/** Who in the workspace may use one mailbox: by role, and person by person. */
function AccessPanel({ account, onClose }: { account: EmailAccount; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const access = useQuery({ queryKey: ['mailbox-access', account.id], queryFn: () => api.mailboxAccess(account.id) });
  const [mode, setMode] = useState<'everyone' | 'restricted'>('everyone');
  const [roleLevels, setRoleLevels] = useState<Record<string, Level>>({});
  const [levels, setLevels] = useState<Record<number, Level>>({});
  // Filled in once; later refreshes (after a role change) must not throw away what is being edited.
  const loaded = useRef(false);
  useEffect(() => {
    if (!access.data || loaded.current) return;
    loaded.current = true;
    setMode(access.data.access_mode);
    setRoleLevels(Object.fromEntries(access.data.roles.filter((r) => !r.always).map((r) => [r.role, r.permission ?? 'none'])));
    setLevels(Object.fromEntries(access.data.members.filter((m) => !m.always).map((m) => [m.user_id, m.permission ?? 'none'])));
  }, [access.data]);

  const save = useMutation({
    mutationFn: () => api.setMailboxAccess(account.id, {
      access_mode: mode,
      roles: Object.entries(roleLevels).filter(([, level]) => level !== 'none').map(([role, level]) => ({ role: role as Role, permission: level as MailboxPermission })),
      members: Object.entries(levels).filter(([, level]) => level !== 'none').map(([userId, level]) => ({ user_id: Number(userId), permission: level as MailboxPermission })),
    }),
    onSuccess: (saved) => {
      client.setQueryData(['mailbox-access', account.id], saved);
      client.invalidateQueries({ queryKey: ['email-accounts'] });
      toast(saved.access_mode === 'restricted' ? `Only the chosen roles and people can use ${account.email_address} now.` : `Everyone in the workspace can use ${account.email_address} now.`);
      onClose();
    },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not save who can use this mailbox.'),
  });

  const team = useQuery({ queryKey: ['members'], queryFn: api.members });
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<Role>('agent');
  const [inviteUrl, setInviteUrl] = useState<{ email: string; url: string } | null>(null);
  const refreshTeam = () => {
    client.invalidateQueries({ queryKey: ['members'] });
    client.invalidateQueries({ queryKey: ['mailbox-access', account.id] });
    client.invalidateQueries({ queryKey: ['invitations'] });
  };
  const changeRole = useMutation({
    mutationFn: ({ id, role }: { id: number; role: Role }) => api.updateMemberRole(id, role),
    onSuccess: () => { refreshTeam(); toast('Role updated.'); },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not change the role.'),
  });
  const invite = useMutation({
    mutationFn: () => api.createInvitation({ email: inviteEmail.trim(), role: inviteRole }),
    onSuccess: (invitation) => { setInviteUrl({ email: invitation.email, url: invitation.invite_url }); setInviteEmail(''); refreshTeam(); },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not create the invitation.'),
  });
  const ASSIGNABLE: Role[] = ['admin', 'manager', 'agent', 'viewer'];
  const roleNote = (role: Role) => access.data?.roles.find((r) => r.role === role)?.description ?? '';

  const others = access.data?.members.filter((m) => !m.always) ?? [];
  const person = (m: MailboxAccessMember) => (
    <div className="table-person"><span><b>{m.name}</b><small>{m.email} · {titleCase(m.role)}</small></span></div>
  );
  // What a person ends up with: the higher of their role's access and their own.
  const viaRole = (m: MailboxAccessMember): Level => roleLevels[m.role] ?? 'none';

  return (
    <div className="access-panel" data-testid={`panel-access-${account.id}`}>
      <div className="access-head">
        <div><b>Who can use {account.email_address}</b><small>People without access do not see this mailbox or any of its mail.</small></div>
      </div>
      {access.isLoading ? <SkeletonRows rows={2} /> : access.isError || !access.data ? <div className="form-error">Could not load who has access. Try again.</div> : (
        <>
          <div className="access-modes" role="radiogroup" aria-label="Who can use this mailbox">
            <label className={mode === 'everyone' ? 'picked' : ''}>
              <input type="radio" name={`mode-${account.id}`} checked={mode === 'everyone'} onChange={() => setMode('everyone')} data-testid="radio-everyone" />
              <span><b>Everyone in the workspace</b><small>Each person can do what their role allows: viewers read, everyone else reads and sends.</small></span>
            </label>
            <label className={mode === 'restricted' ? 'picked' : ''}>
              <input type="radio" name={`mode-${account.id}`} checked={mode === 'restricted'} onChange={() => setMode('restricted')} data-testid="radio-restricted" />
              <span><b>Only chosen roles and people</b><small>Choose below which roles can read it and which can also send from it.</small></span>
            </label>
          </div>

          <div className="access-title">Team members <small>Add people to this workspace and give each a role.</small></div>
          <div className="access-people" data-testid="list-team">
            {team.data?.map((m) => (
              <div className="access-person" key={m.id} data-testid={`team-member-${m.user_id}`}>
                <div className="table-person"><span><b>{m.name}{m.is_you ? ' (you)' : ''}</b><small>{m.email}</small></span></div>
                {m.role === 'owner' ? (
                  <span className="role-pill">Owner · always has access</span>
                ) : (
                  <select value={m.role} onChange={(e) => changeRole.mutate({ id: m.id, role: e.target.value as Role })} disabled={changeRole.isPending}
                    aria-label={`Role of ${m.name}`} data-testid={`select-team-role-${m.user_id}`}>
                    {ASSIGNABLE.map((role) => <option key={role} value={role}>{titleCase(role)} · {roleNote(role)}</option>)}
                  </select>
                )}
              </div>
            ))}
            <form className="access-person access-invite" onSubmit={(e) => { e.preventDefault(); if (inviteEmail.trim()) invite.mutate(); }}>
              <input type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder="Add a team member by email" aria-label="Email of the person to add" data-testid="input-team-email" />
              <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as Role)} aria-label="Role for the new person" data-testid="select-team-new-role">
                {ASSIGNABLE.map((role) => <option key={role} value={role}>{titleCase(role)}</option>)}
              </select>
              <Button kind="primary" type="submit" disabled={!inviteEmail.trim() || invite.isPending} testId="button-team-invite"><UserPlus size={15} /> {invite.isPending ? 'Adding…' : 'Add'}</Button>
            </form>
            {inviteUrl && (
              <div className="form-note" data-testid="notice-team-invited">
                Invitation ready for <b>{inviteUrl.email}</b>. Send them this link; they join with the role you chose.
                <div className="access-link"><code>{inviteUrl.url}</code>
                  <Button onClick={() => { navigator.clipboard.writeText(inviteUrl.url); toast('Link copied.'); }}><Copy size={14} /> Copy</Button>
                </div>
              </div>
            )}
          </div>

          {mode === 'restricted' && (
            <>
              <div className="access-title">Roles</div>
              <div className="access-people" data-testid="list-access-roles">
                {access.data.roles.map((r) => (
                  <div className="access-person" key={r.role} data-testid={`access-role-${r.role}`}>
                    <div className="table-person"><span><b>{r.name}</b><small>{r.description} · {r.people === 1 ? '1 person' : `${r.people} people`}</small></span></div>
                    {r.always ? (
                      <span className="role-pill">Always: read and send</span>
                    ) : (
                      <select value={roleLevels[r.role] ?? 'none'} onChange={(e) => setRoleLevels((prev) => ({ ...prev, [r.role]: e.target.value as Level }))}
                        aria-label={`Access for the ${r.name} role`} data-testid={`select-role-${r.role}`}>
                        <option value="none">No access</option>
                        <option value="read">Can read</option>
                        {r.role !== 'viewer' && <option value="send">Can read and send</option>}
                      </select>
                    )}
                  </div>
                ))}
              </div>

              <div className="access-title">People <small>Give one person more than their role has.</small></div>
              <div className="access-people">
                {others.map((m) => (
                  <div className="access-person" key={m.user_id}>
                    {person(m)}
                    <div className="access-person-pick">
                      {viaRole(m) !== 'none' && <small>Through their role: {viaRole(m) === 'send' && m.role !== 'viewer' ? 'reads and sends' : 'reads'}</small>}
                      <select value={levels[m.user_id] ?? 'none'} onChange={(e) => setLevels((prev) => ({ ...prev, [m.user_id]: e.target.value as Level }))}
                        aria-label={`Access for ${m.name}`} data-testid={`select-access-${m.user_id}`}>
                        <option value="none">{viaRole(m) === 'none' ? 'No access' : 'Same as their role'}</option>
                        <option value="read">Can read</option>
                        {m.role !== 'viewer' && <option value="send">Can read and send</option>}
                      </select>
                    </div>
                  </div>
                ))}
                {others.length === 0 && <div className="form-note">There is nobody besides owners and admins in the workspace yet. Add a team member above; they get the access their role has here.</div>}
              </div>
            </>
          )}

          <div className="settings-form-footer">
            <span>Owners and admins can always use every mailbox. Pending invitations are on the <Link href="/team" className="text-link">Team page</Link>.</span>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <Button onClick={onClose}>Cancel</Button>
              <Button kind="primary" onClick={() => save.mutate()} disabled={save.isPending} testId="button-save-access">{save.isPending ? 'Saving…' : 'Save access'}</Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function AddAccountPage({ provider }: { provider?: string }) {
  const [, navigate] = useLocation();
  const [selectedProvider, setSelectedProvider] = useState<'imap' | 'gmail' | 'microsoft'>(
    (provider as any) || 'imap'
  );

  return (
    <>
      <div style={{ marginBottom: '1.25rem' }}>
        <Link href="/accounts" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', opacity: 0.8, textDecoration: 'none', fontSize: '0.9rem' }}>
          <ArrowLeft size={16} /> Back to email accounts
        </Link>
      </div>

      <PageHeading eyebrow="CONNECTED" title="Connect email account" description="Link an email account to receive and send emails with your team." />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div
          onClick={() => setSelectedProvider('imap')}
          style={{
            cursor: 'pointer',
            padding: '1.25rem',
            borderRadius: '12px',
            border: selectedProvider === 'imap' ? '2px solid rgba(59,130,246,0.8)' : '1px solid rgba(255,255,255,0.1)',
            background: selectedProvider === 'imap' ? 'rgba(59,130,246,0.1)' : 'rgba(255,255,255,0.03)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <b style={{ fontSize: '1.1rem' }}>IMAP / SMTP</b>
            {selectedProvider === 'imap' && <Check size={18} color="#3b82f6" />}
          </div>
          <p style={{ opacity: 0.8, fontSize: '0.875rem' }}>Connect any standard email provider, self-hosted server, or custom domain.</p>
        </div>

        <div
          onClick={() => setSelectedProvider('gmail')}
          style={{
            cursor: 'pointer',
            padding: '1.25rem',
            borderRadius: '12px',
            border: selectedProvider === 'gmail' ? '2px solid rgba(59,130,246,0.8)' : '1px solid rgba(255,255,255,0.1)',
            background: selectedProvider === 'gmail' ? 'rgba(59,130,246,0.1)' : 'rgba(255,255,255,0.03)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <b style={{ fontSize: '1.1rem' }}>Google / Gmail</b>
            {selectedProvider === 'gmail' && <Check size={18} color="#3b82f6" />}
          </div>
          <p style={{ opacity: 0.8, fontSize: '0.875rem' }}>Connect Gmail or Google Workspace by signing in with Google.</p>
        </div>

        <div
          onClick={() => setSelectedProvider('microsoft')}
          style={{
            cursor: 'pointer',
            padding: '1.25rem',
            borderRadius: '12px',
            border: selectedProvider === 'microsoft' ? '2px solid rgba(59,130,246,0.8)' : '1px solid rgba(255,255,255,0.1)',
            background: selectedProvider === 'microsoft' ? 'rgba(59,130,246,0.1)' : 'rgba(255,255,255,0.03)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <b style={{ fontSize: '1.1rem' }}>Microsoft 365 / Outlook</b>
            {selectedProvider === 'microsoft' && <Check size={18} color="#3b82f6" />}
          </div>
          <p style={{ opacity: 0.8, fontSize: '0.875rem' }}>Connect Outlook.com, Hotmail, or Microsoft 365 exchange mailbox.</p>
        </div>
      </div>

      {selectedProvider === 'gmail' && <GoogleConnectPanel />}
      {/* Remounted per provider so the form's server defaults follow the choice. */}
      <AccountForm key={selectedProvider} provider={selectedProvider} onDone={() => navigate('/accounts')} />
    </>
  );
}

function GoogleConnectPanel() {
  const providers = useQuery({ queryKey: ['email-providers'], queryFn: api.emailProviders });
  const googleConnect = useGoogleConnect();

  return (
    <section className="panel settings-main" style={{ marginBottom: '1.25rem' }} data-testid="panel-google-connect">
      <div className="settings-form-head">
        <span className="settings-form-icon"><Mail size={21} /></span>
        <div>
          <h2>Sign in with Google</h2>
          <p>Google asks you to approve reading and sending mail for this mailbox. No password is typed here or stored.</p>
        </div>
      </div>

      {providers.isLoading ? (
        <SkeletonRows rows={1} />
      ) : providers.data?.google_oauth ? (
        <div className="settings-form-footer">
          <span>You can connect several Gmail mailboxes; repeat this for each one.</span>
          <Button kind="primary" onClick={() => googleConnect.mutate()} disabled={googleConnect.isPending} testId="button-google-connect">
            {googleConnect.isPending ? 'Opening Google…' : 'Sign in with Google'}
          </Button>
        </div>
      ) : (
        <div className="form-note" data-testid="notice-google-not-configured">
          <b>Connecting with Google isn’t set up on this server yet.</b> It needs a Google Cloud OAuth client: put its ID and secret in
          {' '}<code>GOOGLE_CLIENT_ID</code> and <code>GOOGLE_CLIENT_SECRET</code> in the server’s <code>.env</code>, and register this redirect address with Google:
          {' '}<code style={{ overflowWrap: 'anywhere' }}>{providers.data?.google_redirect_uri}</code>. The steps are in the README. Until then, a Gmail mailbox can be connected with an app password below.
        </div>
      )}
    </section>
  );
}

function AccountForm({ provider, onDone }: { provider: 'imap' | 'gmail' | 'microsoft'; onDone: () => void }) {
  const toast = useToast();
  const client = useQueryClient();

  const isGmail = provider === 'gmail';
  const isOutlook = provider === 'microsoft';

  const defaultIncomingHost = isGmail ? 'imap.gmail.com' : isOutlook ? 'outlook.office365.com' : '';
  const defaultOutgoingHost = isGmail ? 'smtp.gmail.com' : isOutlook ? 'smtp.office365.com' : '';

  const [emailAddress, setEmailAddress] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');

  const [incomingHost, setIncomingHost] = useState(defaultIncomingHost);
  const [incomingPort, setIncomingPort] = useState(993);
  const [incomingSecurity, setIncomingSecurity] = useState<'ssl' | 'starttls'>('ssl');

  const [outgoingHost, setOutgoingHost] = useState(defaultOutgoingHost);
  const [outgoingPort, setOutgoingPort] = useState(587);
  const [outgoingSecurity, setOutgoingSecurity] = useState<'ssl' | 'starttls'>('starttls');

  const [customServerConfig, setCustomServerConfig] = useState(!isGmail && !isOutlook);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const connectMutation = useMutation({
    mutationFn: (data: ConnectAccountData) => api.connectEmailAccount(data),
    onSuccess: (acc) => {
      client.invalidateQueries({ queryKey: ['email-accounts'] });
      toast(`Successfully connected ${acc.email_address}!`);
      onDone();
    },
    onError: (err) => {
      setErrorMsg(err instanceof ApiError ? err.message : 'Connection test failed. Please verify your credentials.');
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setErrorMsg(null);

    const hostIn = isGmail ? 'imap.gmail.com' : isOutlook ? 'outlook.office365.com' : incomingHost;
    const hostOut = isGmail ? 'smtp.gmail.com' : isOutlook ? 'smtp.office365.com' : outgoingHost;

    connectMutation.mutate({
      provider,
      email_address: emailAddress.trim(),
      display_name: displayName.trim() || emailAddress.trim(),
      incoming_host: hostIn,
      incoming_port: incomingPort,
      incoming_security: incomingSecurity,
      incoming_username: emailAddress.trim(),
      incoming_password: password,
      outgoing_host: hostOut,
      outgoing_port: outgoingPort,
      outgoing_security: outgoingSecurity,
      outgoing_username: emailAddress.trim(),
      outgoing_password: password,
    });
  }

  return (
    <form className="panel settings-main" onSubmit={submit}>
      <div className="settings-form-head">
        <span className="settings-form-icon"><Mail size={21} /></span>
        <div>
          <h2>{isGmail ? 'Or connect Gmail with an app password' : `${titleCase(provider)} connection details`}</h2>
          <p>Credentials are verified live and encrypted at rest using AES authentication.</p>
        </div>
      </div>

      {isGmail && (
        <div style={{ padding: '0.85rem 1rem', background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.25)', borderRadius: '8px', marginBottom: '1.25rem', fontSize: '0.875rem' }}>
          <b style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}><Info size={16} /> Quick Setup for Google / Gmail:</b>
          <span>Google requires an <b>App Password</b> rather than your personal account password. Go to your Google Account &gt; Security &gt; 2-Step Verification &gt; App Passwords, generate a 16-character code, and paste it below.</span>
        </div>
      )}

      {errorMsg && (
        <div className="auth-notice auth-notice-error" style={{ marginBottom: '1.25rem' }}>
          <span>{errorMsg}</span>
        </div>
      )}

      <div className="form-two">
        <Field label="Email address" value={emailAddress} onChange={setEmailAddress} type="email" placeholder="you@company.com" />
        <Field label="Display name" value={displayName} onChange={setDisplayName} placeholder="Support / Sales / Your Name" />
      </div>

      <Field
        label={isGmail ? 'Gmail App Password (16 characters)' : 'Password'}
        value={password}
        onChange={setPassword}
        type="password"
        placeholder={isGmail ? 'xxxx xxxx xxxx xxxx' : 'Mailbox password'}
      />

      {(!isGmail && !isOutlook) || customServerConfig ? (
        <>
          <div style={{ marginTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '1rem' }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.75rem' }}>Incoming Mail Server (IMAP)</h3>
            <div className="form-two">
              <Field label="IMAP Host" value={incomingHost} onChange={setIncomingHost} placeholder="mail.yourcompany.com" />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <Field label="Port" value={String(incomingPort)} onChange={(v) => setIncomingPort(Number(v) || 993)} type="number" />
                <div className="field">
                  <label><span>Security</span>
                    <select
                      value={incomingSecurity}
                      onChange={(e) => setIncomingSecurity(e.target.value as any)}
                      style={{ width: '100%', height: '42px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '0 10px', color: 'inherit' }}
                    >
                      <option value="ssl" style={{ color: '#000' }}>SSL / TLS</option>
                      <option value="starttls" style={{ color: '#000' }}>STARTTLS</option>
                    </select>
                  </label>
                </div>
              </div>
            </div>
          </div>

          <div style={{ marginTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '1rem' }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.75rem' }}>Outgoing Mail Server (SMTP)</h3>
            <div className="form-two">
              <Field label="SMTP Host" value={outgoingHost} onChange={setOutgoingHost} placeholder="smtp.yourcompany.com" />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <Field label="Port" value={String(outgoingPort)} onChange={(v) => setOutgoingPort(Number(v) || 587)} type="number" />
                <div className="field">
                  <label><span>Security</span>
                    <select
                      value={outgoingSecurity}
                      onChange={(e) => setOutgoingSecurity(e.target.value as any)}
                      style={{ width: '100%', height: '42px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '0 10px', color: 'inherit' }}
                    >
                      <option value="starttls" style={{ color: '#000' }}>STARTTLS</option>
                      <option value="ssl" style={{ color: '#000' }}>SSL / TLS</option>
                    </select>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div style={{ marginTop: '0.5rem' }}>
          <button type="button" onClick={() => setCustomServerConfig(true)} style={{ background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer', fontSize: '0.85rem', textDecoration: 'underline' }}>
            Customize host and ports (optional)
          </button>
        </div>
      )}

      <div className="settings-form-footer" style={{ marginTop: '1.5rem' }}>
        <span>We will test incoming and outgoing connectivity before saving.</span>
        <Button kind="primary" type="submit" disabled={!emailAddress || !password || connectMutation.isPending}>
          {connectMutation.isPending ? 'Verifying & Connecting…' : 'Test & Connect Account'}
        </Button>
      </div>
    </form>
  );
}
