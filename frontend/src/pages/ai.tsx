// AI assistance: what it made of new mail, the drafts waiting for approval, its settings,
// and the box shown beside a conversation. Draft-only: nothing is sent until a person approves it.
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'wouter';
import { AlertTriangle, Check, CheckCircle2, CircleSlash, Clock3, OctagonX, Pencil, RotateCw, Send, ShieldAlert, Sparkles, X } from 'lucide-react';
import { Button, EmptyState, Metric, PageHeading, SkeletonRows, Switch, useToast } from '@/components/kit';
import { pageDescriptions, pageTitles } from '@/data';
import { api, ApiError, type AiAnalysis, type AiReply } from '@/lib/api';
import { dateTime, timeAgo } from '@/lib/format';
import { canManage, useSession } from '@/lib/session';

const PRIORITY: Record<string, string> = { low: 'Low', medium: 'Medium', high: 'High' };
const RISK: Record<string, string> = {
  legal: 'Legal', financial_dispute: 'Money dispute', refund_or_payment: 'Refund or payment', complaint: 'Complaint', security: 'Security', personal_data: 'Personal data',
  ambiguous: 'Unclear request', unsupported_request: 'No policy for this', unverified_claim: 'Unverified fact', embedded_instructions: 'Tries to instruct the AI', commitment: 'Asks for a commitment', other: 'Other risk',
};
const message = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

function PriorityChip({ value }: { value: string | null }) {
  return value ? <span className={`ol-chip ai-priority ai-priority-${value}`} data-testid="ai-priority">{PRIORITY[value] ?? value} priority</span> : null;
}

/** Success, pending, skipped or failed, said in words. */
function StateChip({ a }: { a: AiAnalysis }) {
  const [kind, label, Icon] = a.status === 'done' ? ['ok', 'Analysed', CheckCircle2] as const
    : a.status === 'skipped' ? ['skip', 'Skipped', CircleSlash] as const
    : a.status === 'gave_up' ? ['bad', 'Failed', AlertTriangle] as const
    : a.status === 'failed' ? ['warn', `Retrying (${a.attempts} of 3)`, RotateCw] as const
    : ['wait', 'Waiting', Clock3] as const;
  return <span className={`ai-state ai-state-${kind}`}><Icon size={14} /> {label}</span>;
}

function Findings({ a }: { a: AiAnalysis }) {
  return (
    <>
      {a.summary && <p className="ai-summary" data-testid="ai-summary">{a.summary}</p>}
      <div className="ol-chips">
        <PriorityChip value={a.priority} />
        {a.reply_required !== null && <span className={`ol-chip ${a.reply_required ? 'ai-needs-reply' : 'ai-no-reply'}`} data-testid="ai-reply-required">{a.reply_required ? 'Reply needed' : 'No reply needed'}</span>}
        {a.confidence !== null && <span className="ol-chip ai-plain">{Math.round(a.confidence * 100)}% sure</span>}
        {a.risk_flags.map((flag) => <span key={flag} className="ol-chip ai-risk"><ShieldAlert size={11} /> {RISK[flag] ?? flag}</span>)}
      </div>
      {a.requested_actions.length > 0 && <ul className="ai-asks">{a.requested_actions.map((ask, i) => <li key={i}>{ask}</li>)}</ul>}
      {a.reason && <p className="ai-reason">{a.reason}</p>}
      {a.error && <p className="ai-error">{a.error}</p>}
    </>
  );
}

function DraftCard({ reply }: { reply: AiReply }) {
  const client = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(reply.body);
  useEffect(() => { setText(reply.body); }, [reply.body]);
  const refresh = () => { client.invalidateQueries({ queryKey: ['ai'] }); client.invalidateQueries({ queryKey: ['conversations'] }); };
  const save = useMutation({ mutationFn: () => api.editAiReply(reply.id, text), onSuccess: () => { setEditing(false); refresh(); toast('Draft saved.'); }, onError: (e) => toast(message(e, 'Could not save the draft.')) });
  // The fingerprint sent is of the text on screen, so the server refuses if the draft changed underneath.
  const approve = useMutation({ mutationFn: () => api.approveAiReply(reply.id, reply.body_hash), onSuccess: () => { refresh(); toast(`Sent to ${reply.to_email}.`); }, onError: (e) => { refresh(); toast(message(e, 'Could not send the reply.')); } });
  const reject = useMutation({ mutationFn: () => api.rejectAiReply(reply.id), onSuccess: () => { refresh(); toast('Draft rejected.'); }, onError: (e) => toast(message(e, 'Could not reject the draft.')) });
  const open = reply.status === 'pending' || reply.status === 'failed';
  const busy = save.isPending || approve.isPending || reject.isPending;
  const a = reply.analysis;

  return (
    <article className={`panel ai-draft ai-draft-${reply.status}`} data-testid={`ai-draft-${reply.id}`}>
      <header>
        <div>
          <Link href={`/inbox?c=${reply.conversation_id}`} className="ai-draft-subject">{a.subject}</Link>
          <small>From {a.sender} · to {reply.account_email} · {timeAgo(reply.created_at)}</small>
        </div>
        <span className={`ai-state ai-state-${reply.status === 'sent' ? 'ok' : reply.status === 'failed' ? 'bad' : reply.status === 'rejected' ? 'skip' : 'wait'}`} data-testid="ai-draft-status">
          {reply.status === 'sent' ? <><CheckCircle2 size={14} /> {reply.auto_sent ? 'Sent automatically' : `Sent${reply.decided_by_name ? ` by ${reply.decided_by_name}` : ''}`}</>
            : reply.status === 'failed' ? <><AlertTriangle size={14} /> Not sent</>
            : reply.status === 'rejected' ? <><CircleSlash size={14} /> Rejected{reply.decided_by_name ? ` by ${reply.decided_by_name}` : ''}</>
            : reply.status === 'sending' ? <><RotateCw size={14} /> Sending…</>
            : <><Clock3 size={14} /> Waiting for approval</>}
        </span>
      </header>
      <Findings a={a} />
      {a.hold_reasons.length > 0 && (
        <div className="ai-hold" data-testid="ai-hold">
          <b><ShieldAlert size={15} /> Read this one carefully</b>
          <ul>{a.hold_reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
        </div>
      )}
      {open && reply.auto_note.length > 0 && a.hold_reasons.length === 0 && (
        <p className="ai-reason" data-testid="ai-auto-note">Not sent automatically: {reply.auto_note.join('; ')}.</p>
      )}
      {reply.status === 'failed' && reply.error && <p className="ai-error" data-testid="ai-draft-error">It was not sent: {reply.error}</p>}
      <div className="ai-reply">
        <small>Suggested reply to {reply.to_email}{reply.edited ? ' · edited by a teammate' : ''}</small>
        {editing && reply.can_send && <AiWriter conversationId={reply.conversation_id} current={text} onResult={(r) => setText(r.body)} />}
        {editing
          ? <textarea value={text} onChange={(e) => setText(e.target.value)} rows={Math.min(16, Math.max(6, text.split('\n').length + 1))} autoFocus data-testid="ai-draft-text" />
          : <pre data-testid="ai-draft-body">{reply.body}</pre>}
      </div>
      {open && (
        <footer>
          {!reply.can_send ? <span className="field-hint">You can read this draft, but only someone who may send from {reply.account_email} can approve it.</span> : editing ? (
            <>
              <Button onClick={() => { setEditing(false); setText(reply.body); }} disabled={busy}>Cancel</Button>
              <Button kind="primary" onClick={() => save.mutate()} disabled={busy || !text.trim()} testId="ai-draft-save">{save.isPending ? 'Saving…' : 'Save draft'}</Button>
            </>
          ) : (
            <>
              <Button onClick={() => reject.mutate()} disabled={busy} testId="ai-draft-reject"><X size={14} /> Reject</Button>
              <Button onClick={() => setEditing(true)} disabled={busy} testId="ai-draft-edit"><Pencil size={14} /> Edit</Button>
              <Button kind="primary" onClick={() => approve.mutate()} disabled={busy} testId="ai-draft-approve"><Send size={14} /> {approve.isPending ? 'Sending…' : reply.status === 'failed' ? 'Approve & try again' : 'Approve & send'}</Button>
            </>
          )}
        </footer>
      )}
      {reply.status === 'sent' && reply.sent_at && <small className="field-hint" title={dateTime(reply.sent_at)}>Accepted by the mail provider {timeAgo(reply.sent_at)}.</small>}
    </article>
  );
}

function Queue() {
  const [which, setWhich] = useState<'waiting' | 'sent' | 'rejected'>('waiting');
  const replies = useQuery({ queryKey: ['ai', 'replies', which], queryFn: () => api.aiReplies(which), refetchInterval: 20000 });
  return (
    <>
      <div className="panel-head ai-head">
        <div><h2>Approval queue</h2><p>Replies the AI drafted that need a person. Each is sent only when someone approves the exact text.</p></div>
        <div className="settings-tabs ai-tabs">
          {(['waiting', 'sent', 'rejected'] as const).map((w) => <button key={w} type="button" className={w === which ? 'selected' : ''} onClick={() => setWhich(w)} data-testid={`ai-tab-${w}`}>{w === 'waiting' ? 'Waiting' : w === 'sent' ? 'Sent' : 'Rejected'}</button>)}
        </div>
      </div>
      <div className="ai-queue" data-testid="ai-queue">
        {replies.isLoading ? <section className="panel"><SkeletonRows rows={3} /></section> : !replies.data?.length ? (
          <section className="panel"><EmptyState bare icon={Check} title={which === 'waiting' ? 'Nothing is waiting for approval' : which === 'sent' ? 'No AI drafts have been sent' : 'No drafts have been rejected'}>
            {which === 'waiting' ? 'When the AI drafts a reply to a new email, it appears here for you to approve, edit or reject.' : ''}
          </EmptyState></section>
        ) : replies.data.map((reply) => <DraftCard key={reply.id} reply={reply} />)}
      </div>
    </>
  );
}

function Activity() {
  const activity = useQuery({ queryKey: ['ai', 'activity'], queryFn: api.aiActivity, refetchInterval: 20000 });
  return (
    <>
      <div className="panel-head ai-head"><div><h2>What the AI did</h2><p>The most recent 50 emails it looked at, with the outcome of each.</p></div></div>
      <section className="panel collab-list" data-testid="ai-activity">
        {activity.isLoading ? <SkeletonRows rows={3} /> : !activity.data?.length
          ? <EmptyState bare icon={Sparkles} title="Nothing analysed yet">New email is analysed as it arrives once AI assistance is on. You can also open a conversation and choose “Analyse with AI”.</EmptyState>
          : activity.data.map((a) => (
            <Link key={a.id} href={`/inbox?c=${a.conversation_id}`} className="collab-notification ai-activity-row" data-testid={`ai-activity-${a.id}`}>
              <span className="collab-note-text">
                <b>{a.subject} <em>from {a.sender}</em></b>
                <small>{a.summary ?? a.reason ?? a.error ?? 'Waiting to be analysed.'}</small>
                <span className="ol-chips">
                  <StateChip a={a} />
                  <PriorityChip value={a.priority} />
                  {a.reply_required !== null && <span className={`ol-chip ${a.reply_required ? 'ai-needs-reply' : 'ai-no-reply'}`}>{a.reply_required ? 'Reply needed' : 'No reply needed'}</span>}
                  {a.reply_status && <span className="ol-chip ai-plain">Draft: {a.reply_status === 'pending' ? 'waiting for approval' : a.reply_status === 'failed' ? 'not sent' : a.reply_status}</span>}
                </span>
                <time title={dateTime(a.created_at)}>{timeAgo(a.created_at)} · {a.account_email}</time>
              </span>
            </Link>
          ))}
      </section>
    </>
  );
}

function Notice() {
  const { role } = useSession();
  const status = useQuery({ queryKey: ['ai', 'status'], queryFn: api.aiStatus, refetchInterval: 20000 });
  const s = status.data;
  if (!s || (s.configured && s.enabled && !s.paused)) return null;
  const [title, text] = !s.configured ? ['AI is not set up yet', 'The server needs a Gemini key before AI can run. Add GEMINI_API_KEY to the .env file and restart the app.']
    : s.paused ? ['AI activity is stopped', 'The emergency stop is on. Nothing is being analysed or drafted.']
    : ['AI assistance is off', 'Nothing is analysed until it is switched on.'];
  return (
    <div className="welcome-strip auto-off" data-testid="ai-notice">
      <div className="welcome-icon">{s.paused ? <OctagonX size={23} /> : <CircleSlash size={23} />}</div>
      <div><b>{title}</b><p>{text} {s.configured && (canManage(role) ? <Link href="/settings/ai" className="text-link">Open AI controls</Link> : 'An owner or admin can change this in Settings.')}</p></div>
    </div>
  );
}

/** Queues the latest emails already in each mailbox for analysis, when an owner or admin asks. */
function AnalyseRecent({ workingNow }: { workingNow: number }) {
  const client = useQueryClient();
  const toast = useToast();
  const [count, setCount] = useState(100);
  const [result, setResult] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () => api.analyseRecent(count),
    onSuccess: (r) => {
      const left = [r.automated ? `${r.automated.toLocaleString()} from automated senders were left out` : '', r.already_done ? `${r.already_done.toLocaleString()} were already analysed` : ''].filter(Boolean).join(' and ');
      setResult(r.queued === 0 ? `Nothing new to analyse in the latest ${r.looked_at.toLocaleString()} emails${left ? `: ${left}` : ''}.`
        : `${r.queued.toLocaleString()} ${r.queued === 1 ? 'email is' : 'emails are'} queued, about ${Math.max(1, Math.ceil(r.queued / 15))} ${Math.ceil(r.queued / 15) <= 1 ? 'minute' : 'minutes'} of work${left ? `. ${left[0].toUpperCase()}${left.slice(1)}` : ''}.`);
      client.invalidateQueries({ queryKey: ['ai'] });
    },
    onError: (e) => toast(message(e, 'Could not queue the emails.')),
  });
  return (
    <section className="panel auto-recent ai-recent" data-testid="panel-analyse-recent">
      <div>
        <b>Analyse mail you already have</b>
        <p>Summarises and prioritises the latest emails in each mailbox. Automated senders are left out, an email is never analysed twice, and replies are drafted only for mail from the last 14 days.</p>
        {workingNow > 0 && <p className="auto-recent-result" data-testid="text-analyse-progress" aria-live="polite">Working: {workingNow.toLocaleString()} still to analyse. Results appear below as they finish.</p>}
        {result && <p className="ai-reason" data-testid="text-analyse-result" aria-live="polite">{result}</p>}
      </div>
      <div className="auto-recent-go">
        <label>Latest
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} aria-label="How many emails in each mailbox" data-testid="select-analyse-recent">
            {[50, 100, 300, 500].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          in each mailbox
        </label>
        <Button kind="primary" onClick={() => { setResult(null); run.mutate(); }} disabled={run.isPending} testId="button-analyse-recent">{run.isPending ? 'Queuing…' : 'Analyse now'}</Button>
      </div>
    </section>
  );
}

const QUEUE_PATHS = ['/ai', '/ai/auto-reply', '/ai/reply'];
const ACTIVITY_PATHS = ['/ai', '/ai/summary', '/ai/classification', '/ai/priority-sentiment'];
export const AI_PATHS = [...new Set([...QUEUE_PATHS, ...ACTIVITY_PATHS])];

export function AiPage({ path }: { path: string }) {
  const { role } = useSession();
  const status = useQuery({ queryKey: ['ai', 'status'], queryFn: api.aiStatus, refetchInterval: (q) => (q.state.data?.working_now ? 5000 : 20000) });
  const s = status.data;
  const n = (value: number | undefined) => (value === undefined ? '–' : value.toLocaleString());
  return (
    <>
      <PageHeading eyebrow="INTELLIGENCE" title={pageTitles[path]} description={pageDescriptions[path] ?? 'Summaries, priority and reply drafts for new mail. A person approves every reply.'} />
      <Notice />
      {path === '/ai' && (
        <div className="metric-grid">
          <Metric title="Waiting for approval" value={n(s?.waiting_for_approval)} delta="Drafts to read" icon={Clock3} accent="amber" />
          <Metric title="Analysed" value={n(s?.analysed_today)} delta="In the last 24 hours" icon={Sparkles} accent="blue" />
          <Metric title="Replies sent" value={n(s?.sent_today)} delta={s?.auto_sent_today ? `${s.auto_sent_today} automatically, ${s.sent_today - s.auto_sent_today} approved by a person` : 'Approved by a person'} icon={Send} accent="green" />
          <Metric title="Failed" value={n(s?.failed_today)} delta={s?.waiting_for_analysis ? `${s.waiting_for_analysis} still in the queue` : 'Nothing in the queue'} icon={AlertTriangle} accent="violet" />
        </div>
      )}
      {path === '/ai' && canManage(role) && s && s.configured && s.enabled && !s.paused && <AnalyseRecent workingNow={s.working_now} />}
      {QUEUE_PATHS.includes(path) && <Queue />}
      {ACTIVITY_PATHS.includes(path) && <Activity />}
    </>
  );
}

/** Settings > AI controls. */
export function AiControls() {
  const client = useQueryClient();
  const toast = useToast();
  const { role } = useSession();
  const allowed = canManage(role);
  const settings = useQuery({ queryKey: ['ai', 'settings'], queryFn: api.aiSettings });
  const [info, setInfo] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: (body: Parameters<typeof api.updateAiSettings>[0]) => api.updateAiSettings(body),
    onSuccess: (data) => { client.setQueryData(['ai', 'settings'], data); client.invalidateQueries({ queryKey: ['ai'] }); },
    onError: (e) => toast(message(e, 'Could not change the setting.')),
  });
  const s = settings.data;
  if (!s) return <section className="panel settings-main"><SkeletonRows rows={3} /></section>;
  const text = info ?? s.business_info;
  const live = s.configured && s.enabled && !s.paused;
  return (
    <>
      {!s.configured && (
        <div className="welcome-strip auto-off" data-testid="ai-not-set-up">
          <div className="welcome-icon"><CircleSlash size={23} /></div>
          <div><b>AI is not set up yet</b><p>The server needs a Google Gemini key. Add a line <code>GEMINI_API_KEY=…</code> to the <code>.env</code> file in the project folder and restart the app. The key stays on the server and is never shown here.</p></div>
        </div>
      )}
      <section className="panel settings-main auto-controls" data-testid="panel-ai-controls">
        <div className="auto-switch-row auto-switch-main">
          <div><b>AI assistance</b><p>{s.enabled ? `On. Each new email is summarised, given a priority, and a reply is drafted when one is needed (model: ${s.model}).` : 'Off. No email is sent to the AI.'}</p></div>
          <Switch on={s.enabled} onChange={(on) => change.mutate({ enabled: on })} label="AI assistance" disabled={!allowed || change.isPending || (!s.configured && !s.enabled)} testId="switch-ai" />
        </div>
        {s.mailboxes.length > 0 && <h3>Mailboxes</h3>}
        {s.mailboxes.map((m) => (
          <div className="auto-switch-row" key={m.account_id}>
            <div><b>{m.email_address}</b><p>{!live ? 'Not analysed while AI is off or stopped.' : m.enabled ? 'New mail here is analysed.' : 'Mail here is never sent to the AI.'}</p></div>
            <Switch on={live && m.enabled} onChange={(on) => change.mutate({ mailboxes: { [m.account_id]: on } })} label={`AI for ${m.email_address}`} disabled={!allowed || !live || change.isPending} testId={`switch-ai-mailbox-${m.account_id}`} />
          </div>
        ))}
        {!allowed && <p className="field-hint">Only owners and admins can change these.</p>}
      </section>

      <section className="panel settings-main auto-controls ai-auto" data-testid="panel-ai-autosend">
        <div className="auto-switch-row auto-switch-main">
          <div>
            <b>Automatic sending</b>
            <p>Lets the app send a reply with nobody reading it first. A reply goes out by itself only when its priority is switched on here <em>and</em> every safety check passes; anything else waits in the approval queue.</p>
          </div>
        </div>
        <div className="auto-switch-row">
          <div><b>Low priority</b><p>Routine, predictable questions. {s.auto_send_low ? 'On: clean Low replies are sent automatically.' : 'Off: Low replies wait for approval.'}</p></div>
          <Switch on={s.auto_send_low} label="Send Low-priority replies automatically" disabled={!allowed || !live || change.isPending} testId="switch-ai-auto-low"
            onChange={(on) => { if (!on || confirm('Send Low-priority replies automatically?\n\nThe app will send email from your mailboxes without anyone reading it first. You can switch this off, or use the emergency stop, at any time.')) change.mutate({ auto_send_low: on }); }} />
        </div>
        <div className="auto-switch-row">
          <div><b>Medium priority</b><p>Ordinary questions your business information answers. {!s.business_info.trim() ? 'Add business information below before this can be switched on.' : s.auto_send_medium ? 'On: Medium replies that check out against your business information are sent automatically.' : 'Off: Medium replies wait for approval.'}</p></div>
          <Switch on={s.auto_send_medium} label="Send Medium-priority replies automatically" disabled={!allowed || !live || change.isPending || (!s.business_info.trim() && !s.auto_send_medium)} testId="switch-ai-auto-medium"
            onChange={(on) => { if (!on || confirm('Send Medium-priority replies automatically?\n\nThe app will send email from your mailboxes without anyone reading it first, when the reply can be checked against your business information.')) change.mutate({ auto_send_medium: on }); }} />
        </div>
        <div className="auto-switch-row">
          <div><b>High priority</b><p>Sensitive, urgent, disputed or unclear. Always waits for a person. This cannot be changed.</p></div>
          <Switch on={false} onChange={() => undefined} label="High-priority replies always need approval" disabled testId="switch-ai-auto-high" />
        </div>
        <div className="auto-switch-row">
          <div><b>Daily limit</b><p>{s.auto_sent_today} of {s.daily_limit} automatic replies sent in the last 24 hours. Once the limit is reached, the rest wait for approval.</p></div>
          <select className="ai-limit" value={s.daily_limit} onChange={(e) => change.mutate({ daily_limit: Number(e.target.value) })} disabled={!allowed || change.isPending} aria-label="Daily limit for automatic replies" data-testid="select-ai-limit">
            {[...new Set([5, 10, 20, 50, 100, s.daily_limit])].sort((x, y) => x - y).map((v) => <option key={v} value={v}>{v} a day</option>)}
          </select>
        </div>
        {(s.auto_send_low || s.auto_send_medium) && s.mailboxes.map((m) => (
          <div className="auto-switch-row" key={m.account_id}>
            <div><b>{m.email_address}</b><p>{m.auto_send ? 'Automatic replies may be sent from this mailbox.' : 'Nothing is sent automatically from this mailbox.'}</p></div>
            <Switch on={m.auto_send} onChange={(on) => change.mutate({ mailbox_auto_send: { [m.account_id]: on } })} label={`Automatic sending from ${m.email_address}`} disabled={!allowed || change.isPending} testId={`switch-ai-auto-mailbox-${m.account_id}`} />
          </div>
        ))}
        <p className="field-hint">A reply is held for a person if it is High priority, flags any risk, states a figure, link or fact that is not in the thread or your business information, makes a commitment, is long, answers mail more than a day old, or if someone has already replied. Each conversation gets at most one automatic reply a day, and each person three.</p>
      </section>

      <section className={`panel settings-main ai-stop ${s.paused ? 'ai-stop-on' : ''}`} data-testid="panel-ai-stop">
        <div><b><OctagonX size={18} /> Emergency stop</b><p>{s.paused ? 'Stopped. Nothing is being analysed or drafted, and anything waiting in the queue is skipped.' : 'Stops all AI activity at once, for every mailbox: no analysis, no drafting, no automatic sending. Drafts already written stay in the queue; a person can still approve or reject them.'}</p></div>
        <Button kind={s.paused ? 'secondary' : 'primary'} onClick={() => change.mutate({ paused: !s.paused })} disabled={!allowed || change.isPending} testId="button-ai-stop">{s.paused ? 'Let AI resume' : 'Stop all AI now'}</Button>
      </section>

      <form className="panel settings-main collab-form" onSubmit={(e) => { e.preventDefault(); change.mutate({ business_info: text }, { onSuccess: () => { setInfo(null); toast('Business information saved.'); } }); }} data-testid="form-ai-info">
        <label className="field"><span>Business information the AI may use</span>
          <textarea value={text} onChange={(e) => setInfo(e.target.value)} rows={9} maxLength={20000} readOnly={!allowed} placeholder={'Opening hours: Monday to Friday, 9am to 6pm.\nRefunds: within 14 days of purchase, to the original payment method.\nSupport email: help@yourcompany.com'} data-testid="input-ai-info" />
        </label>
        <p className="field-hint">Write the facts and policies you are happy for a reply to state. The AI may use only these and what is in the email thread. If a reply needs a fact that is not here, the draft is marked as unverified and says a teammate will confirm.</p>
        {allowed && <div className="settings-form-footer"><span /><Button kind="primary" type="submit" disabled={change.isPending || info === null || info === s.business_info} testId="button-save-ai-info">Save</Button></div>}
      </form>
    </>
  );
}

/** A small chat box: say what the email should say, and the AI writes or rewrites it. Shown wherever an email is written. */
export function AiWriter({ conversationId, current, onResult }: { conversationId?: number; current: string; onResult: (result: { subject: string; body: string }) => void }) {
  const toast = useToast();
  const status = useQuery({ queryKey: ['ai', 'status'], queryFn: api.aiStatus, staleTime: 30000 });
  const [instruction, setInstruction] = useState('');
  const [asked, setAsked] = useState<string[]>([]);
  const [before, setBefore] = useState<string | null>(null);
  const write = useMutation({
    mutationFn: (text: string) => api.writeWithAi({ instruction: text, current, conversation_id: conversationId }),
    onMutate: () => setBefore(current),
    onSuccess: (result, text) => { onResult(result); setAsked((list) => [...list, text].slice(-4)); setInstruction(''); },
    onError: (e) => { setBefore(null); toast(message(e, 'The AI could not write that just now.')); },
  });
  const s = status.data;
  if (!s || !s.configured || !s.enabled || s.paused) return null;
  const go = () => { const text = instruction.trim(); if (text.length >= 2 && !write.isPending) write.mutate(text); };
  return (
    <div className="ai-writer" data-testid="ai-writer">
      <b><Sparkles size={14} /> Write with AI</b>
      {asked.length > 0 && (
        <ul aria-label="What you asked for">
          {asked.map((text, i) => <li key={i}>{text}</li>)}
        </ul>
      )}
      <div className="ai-writer-row">
        <input value={instruction} onChange={(e) => setInstruction(e.target.value)} maxLength={1000} disabled={write.isPending}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); go(); } }}
          placeholder={current.trim() ? 'Say what to change, e.g. “shorter and friendlier”' : 'Say what the email should say, e.g. “ask for the invoice by Friday”'}
          aria-label="Tell the AI what to write" data-testid="ai-writer-input" />
        <Button kind="primary" onClick={go} disabled={write.isPending || instruction.trim().length < 2} testId="ai-writer-go">{write.isPending ? 'Writing…' : current.trim() ? 'Rewrite' : 'Write'}</Button>
        {before !== null && !write.isPending && asked.length > 0 && (
          <Button onClick={() => { onResult({ subject: '', body: before }); setBefore(null); }} testId="ai-writer-undo">Undo</Button>
        )}
      </div>
      <small>The AI writes it here for you to read and change. Nothing is sent until you send it.</small>
    </div>
  );
}

/** Beside a conversation: what the AI made of its latest email. */
export function AiInsight({ conversationId, readOnly }: { conversationId: number; readOnly: boolean }) {
  const client = useQueryClient();
  const toast = useToast();
  const status = useQuery({ queryKey: ['ai', 'status'], queryFn: api.aiStatus, staleTime: 30000 });
  const live = !!status.data && status.data.configured && status.data.enabled && !status.data.paused;
  const analysis = useQuery({ queryKey: ['ai', 'conversation', conversationId], queryFn: () => api.aiForConversation(conversationId), enabled: !!status.data?.configured });
  const run = useMutation({
    mutationFn: () => api.analyseConversation(conversationId),
    onSuccess: (data) => { client.setQueryData(['ai', 'conversation', conversationId], data); client.invalidateQueries({ queryKey: ['ai'] }); },
    onError: (e) => toast(message(e, 'Could not analyse this conversation.')),
  });
  const a = analysis.data;
  if (!status.data?.configured || (!a && (!live || readOnly))) return null;
  return (
    <section className="ai-insight" data-testid="ai-insight">
      <header>
        <b><Sparkles size={15} /> AI summary</b>
        {a && <StateChip a={a} />}
        {live && !readOnly && (!a || a.status === 'gave_up' || a.status === 'skipped') && (
          <Button onClick={() => run.mutate()} disabled={run.isPending} testId="button-ai-analyse">{run.isPending ? 'Analysing…' : a ? 'Try again' : 'Analyse with AI'}</Button>
        )}
      </header>
      {a ? <Findings a={a} /> : <p className="ai-reason">Not analysed yet. New mail is analysed as it arrives; older mail only when you ask.</p>}
      {a?.reply_id && a.reply_status && (
        <Link href="/ai/auto-reply" className="text-link" data-testid="ai-insight-draft">
          {a.reply_status === 'sent' ? 'The drafted reply was approved and sent.' : a.reply_status === 'rejected' ? 'The drafted reply was rejected.' : 'A drafted reply is waiting for approval.'}
        </Link>
      )}
    </section>
  );
}
