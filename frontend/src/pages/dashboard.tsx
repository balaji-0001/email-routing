import { useQuery } from '@tanstack/react-query';
import { Link } from 'wouter';
import { ArrowRight, Clock3, Inbox, Mail, Users } from 'lucide-react';
import { AlertTriangle, CheckCircle2, Paperclip, RefreshCw } from 'lucide-react';
import { Avatar, EmptyState, Metric, PageHeading, SkeletonRows } from '@/components/kit';
import { api } from '@/lib/api';
import { AutomationOverview } from '@/pages/automation';
import { greeting, longDate, timeAgo } from '@/lib/format';
import { canManage, useSession } from '@/lib/session';

/** "Created the workspace X" reads as "You created the workspace X" in a feed. */
const asSentence = (summary: string) => summary.charAt(0).toLowerCase() + summary.slice(1);

export function Dashboard() {
  const { user, role } = useSession();
  const members = useQuery({ queryKey: ['members'], queryFn: api.members });
  // Only owners and admins may read the audit log, which is what feeds the activity list.
  const activity = useQuery({ queryKey: ['audit-events', 6], queryFn: () => api.auditEvents(6), enabled: canManage(role) });
  const teamSize = members.data?.length;
  const overview = useQuery({ queryKey: ['overview'], queryFn: api.overview, refetchInterval: 20000 });
  const o = overview.data;
  const count = (n: number | undefined) => (n === undefined ? '–' : n.toLocaleString());

  return (
    <>
      <PageHeading
        eyebrow={longDate().toUpperCase()}
        title={`${greeting()}, ${user.first_name}`}
        description="Here’s what’s happening across your shared inboxes."
      />

      {o && o.sync.state !== 'none' && (
        <section className={`sync-panel sync-${o.sync.state}`} data-testid="panel-sync" aria-live="polite">
          <div className="sync-head">
            {o.sync.state === 'syncing' ? <RefreshCw size={20} className="ns-spin" /> : o.sync.state === 'complete' ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
            <div>
              <b data-testid="text-sync-state">
                {o.sync.state === 'syncing' ? 'Syncing your mail…' : o.sync.state === 'complete' ? 'Sync completed' : 'Sync needs attention'}
              </b>
              <small>
                {o.sync.state === 'syncing'
                  ? `${o.sync.stored.toLocaleString()}${o.sync.total ? ` of about ${o.sync.total.toLocaleString()}` : ''} messages are in${o.sync.percent !== null ? ` (${o.sync.percent}%)` : ''}. You can keep working; new mail keeps arriving.`
                  : o.sync.state === 'complete'
                    ? `All ${o.sync.stored.toLocaleString()} messages from ${o.sync.mailboxes.length === 1 ? '1 mailbox' : `${o.sync.mailboxes.length} mailboxes`} are in${o.sync.last_synced_at ? `. Last checked ${timeAgo(o.sync.last_synced_at)}` : ''}. New mail is picked up every minute.`
                    : 'At least one mailbox stopped syncing. Open Email accounts to reconnect it.'}
              </small>
            </div>
          </div>
          {o.sync.state === 'syncing' && o.sync.percent !== null && (
            <div className="sync-bar" role="progressbar" aria-valuenow={o.sync.percent} aria-valuemin={0} aria-valuemax={100} aria-label="Mail sync progress"><i style={{ width: `${o.sync.percent}%` }} /></div>
          )}
          {o.sync.mailboxes.length > 1 || o.sync.state !== 'complete' ? (
            <ul className="sync-list">
              {o.sync.mailboxes.map((m) => (
                <li key={m.email_address} data-testid={`sync-${m.email_address}`}>
                  <span>{m.email_address}</span>
                  <em>
                    {m.state === 'importing' ? `${m.stored.toLocaleString()}${m.total ? ` of about ${m.total.toLocaleString()}` : ''}` : m.state === 'done' ? `${m.stored.toLocaleString()} · Completed` : 'Needs attention'}
                  </em>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      )}
      {o && o.connected_inboxes === 0 && (
        <div className="welcome-strip">
          <div className="welcome-icon"><Inbox size={23} /></div>
          <div>
            <b>No inboxes connected yet</b>
            <p>Your team’s mail shows up here once an email account is connected. <Link href="/accounts/add" className="text-link">Connect an account</Link></p>
          </div>
        </div>
      )}
      {o && o.inboxes_needing_attention > 0 && (
        <div className="welcome-strip" data-testid="notice-inbox-problem">
          <div className="welcome-icon"><AlertTriangle size={23} /></div>
          <div>
            <b>{o.inboxes_needing_attention === 1 ? 'An inbox needs your attention' : `${o.inboxes_needing_attention} inboxes need your attention`}</b>
            <p>It stopped syncing. <Link href="/accounts" className="text-link">Open Email accounts</Link> to reconnect it.</p>
          </div>
        </div>
      )}

      <div className="metric-grid">
        <Metric title="Open conversations" value={count(o?.open_conversations)} delta={o ? `${o.unread_conversations.toLocaleString()} unread` : 'Loading…'} icon={Inbox} accent="blue" />
        <Metric title="Waiting on your team" value={count(o?.waiting_on_team)} delta={o ? (o.waiting_on_team ? 'Marked Pending' : 'Nothing waiting') : 'Loading…'} icon={Clock3} accent="amber" />
        <Metric title="Connected inboxes" value={count(o?.connected_inboxes)} delta={o ? `${o.messages_stored.toLocaleString()} messages stored` : 'Loading…'} icon={Mail} accent="violet" />
        <Metric title="Team members" value={teamSize === undefined ? '–' : String(teamSize)} delta={teamSize === 1 ? 'Just you so far' : 'In this workspace'} icon={Users} accent="green" />
      </div>

      <div className="dashboard-grid">
        <section className="panel overview-panel">
          <div className="panel-head"><div><h2>Needs your attention</h2><p>Unread conversations, newest first, across every account</p></div></div>
          {overview.isLoading ? (
            <SkeletonRows rows={3} />
          ) : o?.needs_attention.length ? (
            <>
              <div className="activity-feed" data-testid="list-needs-attention">
                {o.needs_attention.map((conv) => (
                  <Link href={`/inbox?c=${conv.id}`} className="activity-item" key={conv.id} style={{ textDecoration: 'none', color: 'inherit' }} data-testid={`attention-${conv.id}`}>
                    <Avatar name={conv.last_sender_name || conv.last_sender_email || conv.account_email} />
                    <div className="activity-text">
                      <p><b>{conv.last_sender_name || conv.last_sender_email || conv.account_email}</b> {conv.subject || '(no subject)'}{conv.has_attachments && <Paperclip size={13} style={{ marginLeft: 6, verticalAlign: 'middle' }} />}</p>
                      <small>{timeAgo(conv.last_message_at)} · {conv.account_email}</small>
                    </div>
                  </Link>
                ))}
              </div>
              <Link href="/inbox" className="activity-link">Open the inbox{o.unread_conversations > o.needs_attention.length ? ` (${o.unread_conversations.toLocaleString()} unread)` : ''} <ArrowRight size={16} /></Link>
            </>
          ) : (
            <EmptyState bare icon={Inbox} title={o?.connected_inboxes ? 'Nothing needs your attention' : 'No inbox connected yet'}>
              {o?.connected_inboxes ? 'You have no unread conversations.' : 'Unread conversations will be listed here once an inbox is connected.'}
            </EmptyState>
          )}
        </section>

        <section className="panel activity-panel">
          <div className="panel-head"><div><h2>Team activity</h2><p>What changed in this workspace</p></div></div>
          {activity.isLoading ? (
            <SkeletonRows rows={3} />
          ) : activity.data?.length ? (
            <>
              <div className="activity-feed" data-testid="activity-feed">
                {activity.data.map((event) => (
                  <div className="activity-item" key={event.id}>
                    <Avatar name={event.actor_name ?? '?'} />
                    <div className="activity-text">
                      <p><b>{event.actor_is_you ? 'You' : event.actor_name ?? 'Someone'}</b> {asSentence(event.summary)}</p>
                      <small>{timeAgo(event.created_at)}</small>
                    </div>
                  </div>
                ))}
              </div>
              <Link href="/settings/audit-logs" className="activity-link">See the audit log <ArrowRight size={16} /></Link>
            </>
          ) : (
            <EmptyState bare icon={Users} title="No activity yet">Changes your team makes in this workspace will be listed here.</EmptyState>
          )}
        </section>
      </div>

      <AutomationOverview />
    </>
  );
}
