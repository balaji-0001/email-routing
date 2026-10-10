// Follow-up reminders: the control beside a conversation, and the page listing what is set for later.
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'wouter';
import { AlarmClock, ArrowRight, CalendarClock, X } from 'lucide-react';
import { Button, EmptyState, PageHeading, SkeletonRows, useToast } from '@/components/kit';
import { pageDescriptions, pageTitles } from '@/data';
import { api, ApiError, type Reminder } from '@/lib/api';
import { dateTime, timeAgo } from '@/lib/format';

const WHEN: [string, string, number][] = [['3h', 'In 3 hours', 3], ['1d', 'Tomorrow', 24], ['3d', 'In 3 days', 72], ['7d', 'In a week', 168], ['14d', 'In two weeks', 336]];
const STATE: Record<Reminder['status'], string> = { waiting: 'Waiting', done: 'Reminded', answered: 'They replied first', cancelled: 'Cancelled' };

/** Beside a conversation: set a reminder, or see and cancel the one that is set. */
export function ReminderControl({ conversationId }: { conversationId: number }) {
  const client = useQueryClient();
  const toast = useToast();
  const [onlyIfQuiet, setOnlyIfQuiet] = useState(true);
  const mine = useQuery({ queryKey: ['reminders', conversationId], queryFn: () => api.reminders(conversationId) });
  const refresh = () => client.invalidateQueries({ queryKey: ['reminders'] });
  const oops = (fallback: string) => (err: unknown) => toast(err instanceof ApiError ? err.message : fallback);
  const set = useMutation({
    mutationFn: (hours: number) => api.createReminder({ conversation_id: conversationId, due_at: new Date(Date.now() + hours * 3600_000).toISOString(), only_if_no_reply: onlyIfQuiet }),
    onSuccess: (r) => { refresh(); toast(`Reminder set for ${dateTime(r.due_at)}.`); },
    onError: oops('Could not set the reminder.'),
  });
  const cancel = useMutation({ mutationFn: (id: number) => api.cancelReminder(id), onSuccess: () => { refresh(); toast('Reminder cancelled.'); }, onError: oops('Could not cancel the reminder.') });
  const waiting = mine.data?.[0];

  return (
    <div className="remind" data-testid="reminder-control">
      <AlarmClock size={15} />
      {waiting ? (
        <>
          <span data-testid="text-reminder">Reminder set for {dateTime(waiting.due_at)}{waiting.only_if_no_reply ? ', if they have not replied' : ''}</span>
          <button type="button" onClick={() => cancel.mutate(waiting.id)} disabled={cancel.isPending} data-testid="button-cancel-reminder"><X size={13} /> Cancel</button>
        </>
      ) : (
        <>
          <select value="" onChange={(e) => { const hours = WHEN.find(([key]) => key === e.target.value)?.[2]; if (hours) set.mutate(hours); }} disabled={set.isPending} aria-label="Remind me about this conversation" data-testid="select-reminder">
            <option value="">Remind me…</option>
            {WHEN.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
          <label><input type="checkbox" checked={onlyIfQuiet} onChange={(e) => setOnlyIfQuiet(e.target.checked)} data-testid="check-reminder-quiet" /> only if they have not replied</label>
        </>
      )}
    </div>
  );
}

/** Automation > Scheduled actions: your reminders, and the rules that run on a timer. */
export function ScheduledPage({ path }: { path: string }) {
  const client = useQueryClient();
  const toast = useToast();
  const mine = useQuery({ queryKey: ['reminders', 'all'], queryFn: () => api.reminders(), refetchInterval: 30000 });
  const rules = useQuery({ queryKey: ['automation', 'rules'], queryFn: api.rules });
  const cancel = useMutation({
    mutationFn: (id: number) => api.cancelReminder(id),
    onSuccess: () => { client.invalidateQueries({ queryKey: ['reminders'] }); toast('Reminder cancelled.'); },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not cancel the reminder.'),
  });
  const timed = (rules.data ?? []).filter((r) => r.trigger === 'waiting');

  return (
    <>
      <PageHeading eyebrow="AUTOMATION" title={pageTitles[path]} description={pageDescriptions[path]} />
      <div className="panel-head ai-head"><div><h2>Your reminders</h2><p>Set from any conversation with “Remind me…”. Only you see yours.</p></div></div>
      <section className="panel collab-list" data-testid="list-reminders">
        {mine.isLoading ? <SkeletonRows rows={3} /> : !mine.data?.length
          ? <EmptyState bare icon={AlarmClock} title="No reminders yet">Open a conversation and choose “Remind me…” to be told about it later. You can ask to be reminded only if nobody has written back.</EmptyState>
          : mine.data.map((r) => (
            <div key={r.id} className={`collab-notification remind-row remind-${r.status}`} data-testid={`reminder-${r.id}`}>
              <span className="collab-note-icon"><AlarmClock size={17} /></span>
              <span className="collab-note-text">
                <b><Link href={`/inbox?c=${r.conversation_id}`} className="text-link">{r.subject}</Link></b>
                <small>{r.status === 'waiting' ? `Due ${dateTime(r.due_at)}${r.only_if_no_reply ? ', only if they have not replied' : ''}` : `${STATE[r.status]}${r.finished_at ? ` ${timeAgo(r.finished_at)}` : ''}`}{r.note ? ` · ${r.note}` : ''}</small>
                <time>{r.account_email}</time>
              </span>
              {r.status === 'waiting' && <Button onClick={() => cancel.mutate(r.id)} disabled={cancel.isPending}><X size={14} /> Cancel</Button>}
            </div>
          ))}
      </section>

      <div className="panel-head ai-head"><div><h2>Rules on a timer</h2><p>Rules that act when an email has waited without a reply from your team.</p></div><Link href="/automation" className="activity-link remind-link">Manage rules <ArrowRight size={16} /></Link></div>
      <section className="panel auto-rules" data-testid="list-timed-rules">
        {rules.isLoading ? <SkeletonRows rows={2} /> : timed.length === 0
          ? <EmptyState bare icon={CalendarClock} title="No timed rules yet">In Automation rules, make a rule and choose “When an email has waited with no reply”. For example: after two days, set the priority to urgent and notify someone.</EmptyState>
          : timed.map((rule) => (
            <article className={`auto-rule ${rule.enabled ? '' : 'auto-rule-off'}`} key={rule.id}>
              <i className={`ol-status-dot ${rule.enabled ? 'ol-status-open' : 'ol-status-closed'}`} aria-hidden />
              <div className="auto-rule-text"><b>{rule.name}</b><p>{rule.summary}</p><small>{rule.enabled ? (rule.run_count ? `Ran ${rule.run_count.toLocaleString()} ${rule.run_count === 1 ? 'time' : 'times'}` : 'Has not run yet') : 'Switched off'}</small></div>
            </article>
          ))}
      </section>
    </>
  );
}
