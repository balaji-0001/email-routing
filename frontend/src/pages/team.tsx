import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, ShieldCheck, Trash2, UserPlus, Users } from 'lucide-react';
import { Avatar, Button, EmptyState, Field, PageHeading, SkeletonRows, useToast } from '@/components/kit';
import { pageDescriptions } from '@/data';
import { api, ApiError, type Role } from '@/lib/api';
import { shortDate, timeAgo, titleCase } from '@/lib/format';
import { canManage, useSession } from '@/lib/session';

export function TeamPage() {
  const { role: myRole } = useSession();
  const client = useQueryClient();
  const toast = useToast();
  const members = useQuery({ queryKey: ['members'], queryFn: api.members });
  const count = members.data?.length ?? 0;
  const isManager = canManage(myRole);

  const updateRole = useMutation({
    mutationFn: ({ id, role }: { id: number; role: Role }) => api.updateMemberRole(id, role),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['members'] });
      toast('Member role updated.');
    },
    onError: (err) => {
      toast(err instanceof ApiError ? err.message : 'Could not update role.');
    },
  });

  const removeMember = useMutation({
    mutationFn: (id: number) => api.removeMember(id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['members'] });
      toast('Member removed from workspace.');
    },
    onError: (err) => {
      toast(err instanceof ApiError ? err.message : 'Could not remove member.');
    },
  });

  return (
    <>
      <PageHeading title="Team members" description={pageDescriptions['/team']} />
      <section className="panel table-panel">
        <div className="table-toolbar">
          <div><b>Workspace members</b><span>{members.isLoading ? 'Loading…' : `${count} ${count === 1 ? 'member' : 'members'}`}</span></div>
        </div>
        {members.isLoading ? (
          <SkeletonRows rows={2} />
        ) : members.isError ? (
          <EmptyState bare icon={Users} title="We couldn’t load the team">Refresh the page to try again.</EmptyState>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Member</th><th>Role</th><th>Joined</th><th>Last active</th>{isManager && <th>Actions</th>}</tr></thead>
              <tbody>
                {members.data?.map((member) => (
                  <tr key={member.id} data-testid={`row-member-${member.user_id}`}>
                    <td>
                      <div className="table-person">
                        <Avatar name={member.name} />
                        <span><b>{member.name}{member.is_you && <em className="you-tag">You</em>}</b><small>{member.email}</small></span>
                      </div>
                    </td>
                    <td>
                      {isManager && !member.is_you ? (
                        <select
                          className="role-select"
                          value={member.role}
                          onChange={(e) => updateRole.mutate({ id: member.id, role: e.target.value as Role })}
                          disabled={updateRole.isPending}
                          style={{
                            background: 'rgba(255,255,255,0.08)',
                            border: '1px solid rgba(255,255,255,0.15)',
                            color: 'inherit',
                            padding: '4px 8px',
                            borderRadius: '6px',
                            fontSize: '0.85rem',
                          }}
                        >
                          <option value="owner" style={{ color: '#000' }}>Owner</option>
                          <option value="admin" style={{ color: '#000' }}>Admin</option>
                          <option value="manager" style={{ color: '#000' }}>Manager</option>
                          <option value="agent" style={{ color: '#000' }}>Agent</option>
                          <option value="viewer" style={{ color: '#000' }}>Viewer</option>
                        </select>
                      ) : (
                        <span className="role-pill">{titleCase(member.role)}</span>
                      )}
                    </td>
                    <td>{shortDate(member.joined_at)}</td>
                    <td>{member.last_active_at ? titleCase(timeAgo(member.last_active_at)) : 'Never'}</td>
                    {isManager && (
                      <td>
                        {!member.is_you && (
                          <button
                            type="button"
                            className="icon-button"
                            title="Remove from workspace"
                            onClick={() => {
                              if (confirm(`Remove ${member.name} from the workspace?`)) {
                                removeMember.mutate(member.id);
                              }
                            }}
                            disabled={removeMember.isPending}
                            style={{ color: 'var(--status-bad)' }}
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export function InvitePage() {
  const { workspace, role } = useSession();
  const client = useQueryClient();
  const toast = useToast();
  const [email, setEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<Role>('agent');
  const [lastCreatedUrl, setLastCreatedUrl] = useState<string | null>(null);

  const invitations = useQuery({ queryKey: ['invitations'], queryFn: api.invitations, enabled: canManage(role) });

  const sendInvite = useMutation({
    mutationFn: () => api.createInvitation({ email, role: inviteRole }),
    onSuccess: (invitation) => {
      setLastCreatedUrl(invitation.invite_url);
      setEmail('');
      client.invalidateQueries({ queryKey: ['invitations'] });
      toast(`Invitation created for ${invitation.email}!`);
    },
    onError: (err) => {
      toast(err instanceof ApiError ? err.message : 'Could not create invitation.');
    },
  });

  const revokeInvite = useMutation({
    mutationFn: (id: number) => api.revokeInvitation(id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['invitations'] });
      toast('Invitation revoked.');
    },
    onError: (err) => {
      toast(err instanceof ApiError ? err.message : 'Could not revoke invitation.');
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    sendInvite.mutate();
  }

  function copyLink(url: string) {
    navigator.clipboard.writeText(url);
    toast('Invitation link copied to clipboard!');
  }

  if (!canManage(role)) {
    return (
      <>
        <PageHeading title="Invite your team" description={pageDescriptions['/team/invite']} />
        <EmptyState icon={ShieldCheck} title="Only workspace owners and admins can invite members">
          Ask an owner or admin of {workspace.name} to invite teammates.
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <PageHeading title="Invite your team" description={pageDescriptions['/team/invite']} />

      <form className="panel settings-main" onSubmit={submit} style={{ marginBottom: '1.5rem' }}>
        <div className="settings-form-head">
          <span className="settings-form-icon"><UserPlus size={21} /></span>
          <div><h2>Send an invitation</h2><p>Invite a colleague to join {workspace.name}.</p></div>
        </div>

        <div className="form-two">
          <Field label="Work email" value={email} onChange={setEmail} type="email" placeholder="colleague@company.com" />
          <div className="field">
            <label><span>Role</span>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as Role)}
                style={{
                  width: '100%',
                  height: '42px',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '8px',
                  padding: '0 12px',
                  color: 'inherit',
                  fontSize: '0.9rem',
                }}
              >
                <option value="admin" style={{ color: '#000' }}>Admin — Runs the workspace</option>
                <option value="manager" style={{ color: '#000' }}>Manager — Leads a team</option>
                <option value="agent" style={{ color: '#000' }}>Agent — Works conversations</option>
                <option value="viewer" style={{ color: '#000' }}>Viewer — Read-only access</option>
              </select>
            </label>
          </div>
        </div>

        <div className="settings-form-footer">
          <span>Invitations remain active for 7 days.</span>
          <Button kind="primary" type="submit" disabled={!email || sendInvite.isPending}>
            {sendInvite.isPending ? 'Inviting…' : 'Send invitation'}
          </Button>
        </div>

        {lastCreatedUrl && (
          <div style={{ marginTop: '1rem', padding: '0.75rem 1rem', background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.2)', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
            <div style={{ overflow: 'hidden' }}>
              <b style={{ display: 'block', fontSize: '0.85rem' }}>Shareable invite link:</b>
              <small style={{ wordBreak: 'break-all', opacity: 0.85 }}>{lastCreatedUrl}</small>
            </div>
            <Button kind="secondary" type="button" onClick={() => copyLink(lastCreatedUrl)}>
              <Copy size={15} /> Copy link
            </Button>
          </div>
        )}
      </form>

      <section className="panel table-panel">
        <div className="table-toolbar">
          <div><b>Pending invitations</b><span>{invitations.data ? `${invitations.data.length} pending` : 'Loading…'}</span></div>
        </div>
        {invitations.isLoading ? (
          <SkeletonRows rows={2} />
        ) : !invitations.data?.length ? (
          <EmptyState bare icon={UserPlus} title="No pending invitations">
            Invitations you send will appear here until they are accepted or expire.
          </EmptyState>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Email</th><th>Role</th><th>Invited by</th><th>Expires</th><th>Actions</th></tr></thead>
              <tbody>
                {invitations.data.map((inv) => (
                  <tr key={inv.id}>
                    <td><b>{inv.email}</b></td>
                    <td><span className="role-pill">{titleCase(inv.role)}</span></td>
                    <td>{inv.invited_by_name ?? 'Admin'}</td>
                    <td>{shortDate(inv.expires_at)}</td>
                    <td>
                      {/* The link is shown once, when the invitation is made. To get a new one, revoke and invite again. */}
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <Button kind="secondary" onClick={() => revokeInvite.mutate(inv.id)} disabled={revokeInvite.isPending}>
                          Revoke
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

const ROLES: { role: Role; summary: string }[] = [
  { role: 'owner', summary: 'Created the workspace' },
  { role: 'admin', summary: 'Runs the workspace' },
  { role: 'manager', summary: 'Leads a team' },
  { role: 'agent', summary: 'Works conversations' },
  { role: 'viewer', summary: 'Read-only access' },
];

const PERMISSIONS: { name: string; roles: Role[] }[] = [
  { name: 'Sign in and see the workspace', roles: ['owner', 'admin', 'manager', 'agent', 'viewer'] },
  { name: 'See team members', roles: ['owner', 'admin', 'manager', 'agent', 'viewer'] },
  { name: 'Change workspace settings', roles: ['owner', 'admin'] },
  { name: 'Invite and remove members', roles: ['owner', 'admin'] },
  { name: 'Connect and manage email accounts', roles: ['owner', 'admin'] },
  { name: 'Read and work conversations', roles: ['owner', 'admin', 'manager', 'agent'] },
  { name: 'Compose and send mail', roles: ['owner', 'admin', 'manager', 'agent'] },
  { name: 'Read the audit log', roles: ['owner', 'admin'] },
];

export function RolesPage() {
  const { role: yours } = useSession();
  return (
    <>
      <PageHeading title="Roles & permissions" description={pageDescriptions['/team/roles']} />
      <div className="role-intro"><ShieldCheck size={21} /><p>You are {yours === 'manager' || yours === 'viewer' ? 'a' : 'an'} {yours} of this workspace. Roles control actions in the workspace.</p></div>
      <div className="panel permission-panel">
        <div className="permission-heading"><div><h2>Permission matrix</h2><p>What each workspace role can do</p></div></div>
        <div className="permission-table-wrap">
          <table className="permission-table">
            <thead>
              <tr>
                <th>Permission</th>
                {ROLES.map(({ role, summary }) => <th key={role}><b>{titleCase(role)}</b><small>{summary}</small></th>)}
              </tr>
            </thead>
            <tbody>
              {PERMISSIONS.map((permission) => (
                <tr key={permission.name}>
                  <td>{permission.name}</td>
                  {ROLES.map(({ role }) => (
                    <td key={role}>
                      {permission.roles.includes(role)
                        ? <span className="permission-yes" aria-label="Allowed"><Check size={16} /></span>
                        : <span className="permission-no" aria-label="Not allowed">—</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
