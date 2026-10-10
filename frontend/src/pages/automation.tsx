// Rules that act on new mail: the list, the editor, a dry run, the history, the ON/OFF switches,
// and the summary shown on the Overview.
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'wouter';
import { AlertTriangle, ArrowDown, ArrowRight, ArrowUp, CheckCircle2, CircleSlash, FlaskConical, Pencil, Plus, RotateCw, Trash2, Workflow, X } from 'lucide-react';
import { Button, EmptyState, PageHeading, SkeletonRows, Switch, useToast } from '@/components/kit';
import { pageDescriptions, pageTitles } from '@/data';
import {
  api, ApiError, type ConversationStatus, type Label, type LabelColor, type Member, type Priority, type Rule, type RuleAction, type RuleBody, type RuleRun, type RuleTest,
} from '@/lib/api';
import { dateTime, timeAgo } from '@/lib/format';
import { canManage, useSession } from '@/lib/session';

type ActionType = RuleAction['type'];

const ACTION_NAMES: [ActionType, string][] = [
  ['add_label', 'Add a label'],
  ['set_priority', 'Set the priority'],
  ['set_status', 'Set the status'],
  ['assign', 'Assign to a person'],
  ['assign_in_turn', 'Share out in turn'],
  ['flag', 'Flag it'],
  ['archive', 'Archive it'],
  ['notify', 'Notify a person'],
];
const PRIORITIES: [Priority, string][] = [['urgent', 'Urgent'], ['high', 'High'], ['normal', 'Normal'], ['low', 'Low']];
const STATUSES: [ConversationStatus, string][] = [['open', 'Open'], ['pending', 'Pending'], ['closed', 'Closed']];

/** Each rules page shows the rules that do its kind of thing, and starts a new rule with that action. */
const PAGES: Record<string, { kinds: ActionType[] | null; first: ActionType; empty: string }> = {
  '/automation': { kinds: null, first: 'add_label', empty: 'A rule looks at each new email and, if it matches, does something for you: adds a label, sets a priority, hands it to someone.' },
  '/automation/assignment': { kinds: ['assign', 'assign_in_turn'], first: 'assign', empty: 'Assignment rules hand a new conversation to one person, or share conversations out among several in turn.' },
  '/automation/labels-priority': { kinds: ['add_label', 'set_priority'], first: 'add_label', empty: 'These rules label incoming mail and mark how urgent it is.' },
};

const BLANK_CONDITIONS: RuleBody['conditions'] = { account_id: null, sender: '', recipient: '', subject: '', body: '', has_attachments: null, ai_priority: null };
const WAITS: [number, string][] = [[4, '4 hours'], [24, '1 day'], [48, '2 days'], [72, '3 days'], [168, '1 week'], [336, '2 weeks']];

function freshAction(type: ActionType, labels: Label[], people: Member[]): RuleAction {
  switch (type) {
    case 'add_label': return { type, label_id: labels[0]?.id ?? 0 };
    case 'set_priority': return { type, value: 'high' };
    case 'set_status': return { type, value: 'pending' };
    case 'assign': return { type, user_id: people[0]?.user_id ?? 0 };
    case 'notify': return { type, user_id: people[0]?.user_id ?? 0 };
    case 'assign_in_turn': return { type, user_ids: [] };
    default: return { type };
  }
}

/** Why an action cannot be saved yet, or null when it is complete. */
function problemWith(action: RuleAction): string | null {
  if (action.type === 'add_label' && !action.label_id) return 'Choose a label.';
  if ((action.type === 'assign' || action.type === 'notify') && !action.user_id) return 'Choose a person.';
  if (action.type === 'assign_in_turn' && action.user_ids.length === 0) return 'Choose at least one person.';
  return null;
}

function useAutomationData() {
  const labels = useQuery({ queryKey: ['labels'], queryFn: api.labels });
  const people = useQuery({ queryKey: ['members'], queryFn: api.members });
  const accounts = useQuery({ queryKey: ['email-accounts'], queryFn: api.emailAccounts });
  return { labels: labels.data ?? [], people: people.data ?? [], accounts: accounts.data ?? [] };
}

function RuleEditor({ rule, first, onClose }: { rule: Rule | null; first: ActionType; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const { labels, people, accounts } = useAutomationData();
  const [name, setName] = useState(rule?.name ?? '');
  const [conditions, setConditions] = useState(rule ? { ...BLANK_CONDITIONS, ...rule.conditions } : BLANK_CONDITIONS);
  const [actions, setActions] = useState<RuleAction[]>(rule?.actions ?? [freshAction(first, [], [])]);
  const [error, setError] = useState<string | null>(null);
  const [tested, setTested] = useState<RuleTest | null>(null);

  const [trigger, setTrigger] = useState<RuleBody['trigger']>(rule?.trigger ?? 'new_mail');
  const [waitHours, setWaitHours] = useState(rule?.wait_hours ?? 48);
  const body: RuleBody = { name: name.trim(), enabled: rule?.enabled ?? true, conditions, actions, trigger, wait_hours: trigger === 'waiting' ? waitHours : null };
  const incomplete = actions.map(problemWith).find(Boolean) ?? null;
  const fail = (fallback: string) => (err: unknown) => setError(err instanceof ApiError ? err.message : fallback);
  const save = useMutation({
    mutationFn: () => (rule ? api.updateRule(rule.id, body) : api.createRule(body)),
    onSuccess: () => { client.invalidateQueries({ queryKey: ['automation'] }); toast('Rule saved.'); onClose(); },
    onError: fail('Could not save the rule.'),
  });
  const test = useMutation({ mutationFn: () => api.testRule({ ...body, name: body.name || 'Test' }), onSuccess: setTested, onError: fail('Could not test the rule.') });

  const condition = <K extends keyof RuleBody['conditions']>(key: K, value: RuleBody['conditions'][K]) => { setConditions({ ...conditions, [key]: value }); setTested(null); };
  const setAction = (index: number, action: RuleAction) => setActions(actions.map((a, i) => (i === index ? action : a)));
  const text = (key: 'sender' | 'recipient' | 'subject' | 'body', label: string, placeholder: string) => (
    <label className="field"><span>{label}</span>
      <input value={conditions[key]} onChange={(e) => condition(key, e.target.value)} maxLength={200} placeholder={placeholder} data-testid={`input-rule-${key}`} />
    </label>
  );

  return (
    <form className="panel settings-main collab-form auto-editor" onSubmit={(e) => { e.preventDefault(); setError(null); save.mutate(); }} data-testid="form-rule">
      {error && <div className="form-error" role="alert">{error}</div>}
      <label className="field"><span>Rule name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="Invoices to billing" autoFocus data-testid="input-rule-name" />
      </label>

      <fieldset className="auto-group">
        <legend>When</legend>
        <div className="auto-action">
          <select value={trigger} onChange={(e) => { setTrigger(e.target.value as RuleBody['trigger']); setTested(null); }} aria-label="When the rule runs" data-testid="select-rule-trigger">
            <option value="new_mail">A new email arrives</option>
            <option value="waiting">An email has waited with no reply for…</option>
          </select>
          {trigger === 'waiting' && (
            <select value={waitHours} onChange={(e) => setWaitHours(Number(e.target.value))} aria-label="How long it has waited" data-testid="select-rule-wait">
              {[...new Map([...WAITS, [waitHours, `${waitHours} hours`] as [number, string]].map((w) => [w[0], w])).values()].sort((a, b) => a[0] - b[0]).map(([hours, label]) => <option key={hours} value={hours}>{label}</option>)}
            </select>
          )}
        </div>
        {trigger === 'waiting' && <p className="field-hint">Runs once for an email that is still the last word in an open conversation after that long. Only mail that arrives after you save the rule counts.</p>}
        <p className="field-hint">And only if… Fill in what matters; everything you fill in must be true. Leave it all empty to match every email.</p>
        <div className="auto-grid">
          <label className="field"><span>It came to</span>
            <select value={conditions.account_id ?? ''} onChange={(e) => condition('account_id', e.target.value ? Number(e.target.value) : null)} data-testid="select-rule-account">
              <option value="">Any mailbox</option>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.email_address}</option>)}
            </select>
          </label>
          {text('sender', 'Sender contains', 'billing@ or a name')}
          {text('recipient', 'Sent to contains', 'support@')}
          {text('subject', 'Subject contains', 'invoice')}
          {text('body', 'Message contains', 'refund')}
          <label className="field"><span>Attachments</span>
            <select value={conditions.has_attachments === null ? '' : String(conditions.has_attachments)} onChange={(e) => condition('has_attachments', e.target.value === '' ? null : e.target.value === 'true')} data-testid="select-rule-attachments">
              <option value="">With or without</option><option value="true">Has attachments</option><option value="false">Has none</option>
            </select>
          </label>
          <label className="field"><span>The AI marks it</span>
            <select value={conditions.ai_priority ?? ''} onChange={(e) => condition('ai_priority', (e.target.value || null) as RuleBody['conditions']['ai_priority'])} data-testid="select-rule-ai-priority">
              <option value="">Any priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
            </select>
          </label>
        </div>
        {conditions.ai_priority && <p className="field-hint">AI needs to be on for this: the rule runs once the AI has analysed the email, and never for mail the AI skips.</p>}
      </fieldset>

      <fieldset className="auto-group">
        <legend>Do this</legend>
        {actions.map((action, index) => (
          <div className="auto-action" key={index} data-testid={`rule-action-${index}`}>
            <select value={action.type} onChange={(e) => setAction(index, freshAction(e.target.value as ActionType, labels, people))} aria-label="What to do" data-testid={`select-action-${index}`}>
              {ACTION_NAMES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {action.type === 'add_label' && (labels.length === 0
              ? <span className="field-hint">There are no labels yet. <Link href="/labels" className="text-link">Create one</Link> first.</span>
              : <select value={action.label_id || ''} onChange={(e) => setAction(index, { ...action, label_id: Number(e.target.value) })} aria-label="Label" data-testid={`select-label-${index}`}>
                  <option value="" disabled>Choose a label</option>
                  {labels.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>)}
            {action.type === 'set_priority' && (
              <select value={action.value} onChange={(e) => setAction(index, { ...action, value: e.target.value as Priority })} aria-label="Priority" data-testid={`select-priority-${index}`}>
                {PRIORITIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>)}
            {action.type === 'set_status' && (
              <select value={action.value} onChange={(e) => setAction(index, { ...action, value: e.target.value as ConversationStatus })} aria-label="Status">
                {STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>)}
            {(action.type === 'assign' || action.type === 'notify') && (
              <select value={action.user_id || ''} onChange={(e) => setAction(index, { ...action, user_id: Number(e.target.value) })} aria-label="Person" data-testid={`select-person-${index}`}>
                <option value="" disabled>Choose a person</option>
                {people.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}{m.is_you ? ' (you)' : ''}</option>)}
              </select>)}
            {action.type === 'assign_in_turn' && (
              <span className="auto-people">
                {people.map((m) => (
                  <label key={m.user_id}>
                    <input type="checkbox" checked={action.user_ids.includes(m.user_id)} data-testid={`check-person-${m.user_id}`}
                      onChange={(e) => setAction(index, { ...action, user_ids: e.target.checked ? [...action.user_ids, m.user_id] : action.user_ids.filter((id) => id !== m.user_id) })} />
                    {m.name}
                  </label>
                ))}
              </span>)}
            {actions.length > 1 && <button type="button" className="auto-icon" onClick={() => setActions(actions.filter((_, i) => i !== index))} aria-label="Remove this action"><X size={16} /></button>}
          </div>
        ))}
        {actions.length < 10 && <Button onClick={() => setActions([...actions, freshAction('flag', labels, people)])} testId="button-add-action"><Plus size={14} /> Add another action</Button>}
        <p className="field-hint">Rules only organise mail inside Email Routing. They never send email, and a person who cannot open the mailbox is never given its conversations.</p>
      </fieldset>

      {tested && (
        <div className="auto-test" data-testid="rule-test-result" aria-live="polite">
          <b>{tested.matches.length === 0 ? 'No recent email matches.' : `${tested.matches.length}${tested.matches.length === 25 ? ' or more' : ''} of the ${tested.checked.toLocaleString()} most recent emails match.`}</b>
          <small>This is only a preview. Nothing was changed, and the rule will act only on mail that arrives after it is saved.</small>
          {tested.matches.length > 0 && (
            <ul>{tested.matches.slice(0, 8).map((m, i) => <li key={i}><Link href={`/inbox?c=${m.conversation_id}`} className="text-link">{m.subject}</Link> <span>{m.sender} · {timeAgo(m.sent_at)}</span></li>)}</ul>
          )}
        </div>
      )}

      <div className="settings-form-footer">
        <span>{incomplete ?? ''}</span>
        <div className="collab-actions">
          <Button onClick={() => { setError(null); test.mutate(); }} disabled={!!incomplete || test.isPending} testId="button-test-rule"><FlaskConical size={14} /> {test.isPending ? 'Checking…' : 'Try it on recent mail'}</Button>
          <Button onClick={onClose}>Cancel</Button>
          <Button kind="primary" type="submit" disabled={!name.trim() || !!incomplete || save.isPending} testId="button-save-rule">{save.isPending ? 'Saving…' : 'Save rule'}</Button>
        </div>
      </div>
    </form>
  );
}

function RunRow({ run }: { run: RuleRun }) {
  const Icon = run.status === 'done' ? CheckCircle2 : run.status === 'failed' ? RotateCw : AlertTriangle;
  return (
    <Link href={`/inbox?c=${run.conversation_id}`} className={`collab-notification auto-run auto-run-${run.status}`} data-testid={`run-${run.id}`}>
      <span className="collab-note-icon"><Icon size={17} /></span>
      <span className="collab-note-text">
        <b>{run.rule_name} <em>on {run.subject || '(no subject)'}</em></b>
        <small>
          {run.status === 'done' ? run.done.join(' · ')
            : run.status === 'failed' ? `Did not work (${run.error}). It will be tried again; attempt ${run.attempts} of 3.`
            : `Gave up after ${run.attempts} attempts: ${run.error}`}
        </small>
        <time title={dateTime(run.created_at)}>{timeAgo(run.created_at)}</time>
      </span>
    </Link>
  );
}

function OffNotice({ canSwitch }: { canSwitch: boolean }) {
  return (
    <div className="welcome-strip auto-off" data-testid="notice-automation-off">
      <div className="welcome-icon"><CircleSlash size={23} /></div>
      <div>
        <b>Automation is off</b>
        <p>Rules are saved, but nothing runs until automation is switched on. {canSwitch
          ? <Link href="/settings/automation" className="text-link">Open Automation controls</Link>
          : 'An owner or admin can switch it on in Settings.'}</p>
      </div>
    </div>
  );
}

/** Ready-made rules for common kinds of mail. Each is added through the normal rule and label requests, in this order. */
type Suggestion = { name: string; why: string; conditions: Partial<RuleBody['conditions']>; label?: [string, LabelColor]; priority?: Priority; flag?: boolean; tellMe?: boolean };
const SUGGESTIONS: Suggestion[] = [
  { name: 'LinkedIn updates', why: 'Keeps social notifications out of the way.', conditions: { sender: 'linkedin.com' }, label: ['Social', 'blue'], priority: 'low' },
  { name: 'Shopping offers', why: 'Marks store promotions as low priority.', conditions: { sender: 'myntra.com' }, label: ['Promotions', 'grey'], priority: 'low' },
  { name: 'Job site alerts', why: 'Gathers job alerts under one label.', conditions: { sender: 'naukri.com' }, label: ['Jobs', 'violet'] },
  { name: 'Bank alerts', why: 'Makes messages from your bank stand out.', conditions: { sender: 'sbi.co.in' }, label: ['Bank', 'green'], priority: 'high' },
  { name: 'Invoices and bills', why: 'Labels anything with "invoice" in the subject.', conditions: { subject: 'invoice' }, label: ['Bills', 'amber'] },
  { name: 'Mail from a person', why: 'Mail from a personal Gmail address usually wants an answer.', conditions: { sender: '@gmail.com' }, label: ['follow up', 'teal'], priority: 'high' },
  { name: 'Interviews', why: 'Flags interview mail and tells you straight away.', conditions: { subject: 'interview' }, label: ['Jobs', 'violet'], priority: 'high', flag: true, tellMe: true },
  { name: 'Google security alerts', why: 'Sign-in and security warnings for your Google account.', conditions: { sender: 'accounts.google.com' }, label: ['Security', 'red'], priority: 'urgent', flag: true },
  { name: 'Marked urgent', why: 'Anything with "urgent" in the subject.', conditions: { subject: 'urgent' }, label: ['urgent', 'red'], priority: 'urgent', tellMe: true },
];

function SuggestedRules({ existing }: { existing: Rule[] }) {
  const client = useQueryClient();
  const toast = useToast();
  const { people } = useAutomationData();
  const me = people.find((m) => m.is_you)?.user_id;
  const have = new Set(existing.map((r) => r.name.toLowerCase()));
  const left = SUGGESTIONS.filter((s) => !have.has(s.name.toLowerCase()));

  const add = useMutation({
    mutationFn: async (wanted: Suggestion[]) => {
      // Labels are looked up fresh, so one created for an earlier suggestion is reused by the next.
      const labels = new Map((await api.labels()).map((l) => [l.name.toLowerCase(), l.id]));
      for (const s of wanted) {
        const actions: RuleAction[] = [];
        if (s.label) {
          const [name, color] = s.label;
          if (!labels.has(name.toLowerCase())) labels.set(name.toLowerCase(), (await api.createLabel({ name, color })).id);
          actions.push({ type: 'add_label', label_id: labels.get(name.toLowerCase())! });
        }
        if (s.priority) actions.push({ type: 'set_priority', value: s.priority });
        if (s.flag) actions.push({ type: 'flag' });
        if (s.tellMe && me) actions.push({ type: 'notify', user_id: me });
        await api.createRule({ name: s.name, enabled: true, conditions: { ...BLANK_CONDITIONS, ...s.conditions }, actions, trigger: 'new_mail', wait_hours: null });
      }
      return wanted.length;
    },
    onSuccess: (count) => toast(count === 1 ? 'Rule added.' : `${count} rules added.`),
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not add the rule.'),
    onSettled: () => { client.invalidateQueries({ queryKey: ['automation'] }); client.invalidateQueries({ queryKey: ['labels'] }); },
  });

  if (left.length === 0) return null;
  return (
    <section className="panel auto-suggest" data-testid="panel-suggested-rules">
      <div className="panel-head">
        <div><h2>Suggested rules</h2><p>Ready-made rules for common kinds of mail. Add the ones you want; you can edit or delete them afterwards.</p></div>
        <Button kind="primary" onClick={() => add.mutate(left)} disabled={add.isPending} testId="button-add-all-suggestions">{add.isPending ? 'Adding…' : left.length === 1 ? 'Add it' : `Add all ${left.length}`}</Button>
      </div>
      <ul className="auto-mini">
        {left.map((s) => (
          <li key={s.name} data-testid={`suggestion-${s.name}`}>
            <span><b>{s.name}</b><small>{s.why}</small></span>
            <Button onClick={() => add.mutate([s])} disabled={add.isPending}><Plus size={14} /> Add</Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Applies the rules that are on to mail already in the mailboxes, when an owner or admin asks. */
function RunOnRecent() {
  const client = useQueryClient();
  const toast = useToast();
  const [count, setCount] = useState(100);
  const [result, setResult] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () => api.runRulesOnRecent(count),
    onSuccess: (r) => {
      setResult(`Looked at ${r.checked.toLocaleString()} ${r.checked === 1 ? 'email' : 'emails'}. The rules acted ${r.runs.toLocaleString()} ${r.runs === 1 ? 'time' : 'times'}.`);
      client.invalidateQueries({ queryKey: ['automation'] });
      client.invalidateQueries({ queryKey: ['conversations'] });
    },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not run the rules.'),
  });
  return (
    <section className="panel auto-recent" data-testid="panel-run-recent">
      <div>
        <b>Run on mail you already have</b>
        <p>Applies the rules that are switched on to the latest emails in each mailbox. An email a rule has already handled is not handled twice, and nobody is notified about older mail.</p>
        {result && <p className="auto-recent-result" data-testid="text-run-recent-result" aria-live="polite">{result}</p>}
      </div>
      <div className="auto-recent-go">
        <label>Latest
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} aria-label="How many emails in each mailbox" data-testid="select-run-recent">
            {[50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          in each mailbox
        </label>
        <Button kind="primary" onClick={() => { setResult(null); run.mutate(); }} disabled={run.isPending} testId="button-run-recent">{run.isPending ? 'Running…' : 'Run now'}</Button>
      </div>
    </section>
  );
}

export function AutomationPage({ path }: { path: string }) {
  const page = PAGES[path];
  const client = useQueryClient();
  const toast = useToast();
  const { role } = useSession();
  const canEdit = canManage(role) || role === 'manager';
  const rules = useQuery({ queryKey: ['automation', 'rules'], queryFn: api.rules });
  const settings = useQuery({ queryKey: ['automation', 'settings'], queryFn: api.automationSettings });
  const runs = useQuery({ queryKey: ['automation', 'runs'], queryFn: () => api.ruleRuns(), refetchInterval: 30000, enabled: path === '/automation' });
  const [editing, setEditing] = useState<Rule | 'new' | null>(null);

  const refresh = () => client.invalidateQueries({ queryKey: ['automation'] });
  const oops = (fallback: string) => (err: unknown) => toast(err instanceof ApiError ? err.message : fallback);
  const toggle = useMutation({ mutationFn: (r: Rule) => api.toggleRule(r.id, !r.enabled), onSuccess: refresh, onError: oops('Could not change the rule.') });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteRule(id), onSuccess: () => { refresh(); toast('Rule deleted.'); }, onError: oops('Could not delete the rule.') });
  const reorder = useMutation({ mutationFn: (ids: number[]) => api.reorderRules(ids), onSuccess: refresh, onError: oops('Could not change the order.') });

  const all = rules.data ?? [];
  const shown = page.kinds ? all.filter((r) => r.actions.some((a) => page.kinds!.includes(a.type))) : all;
  const move = (index: number, by: number) => {
    const ids = all.map((r) => r.id);
    [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
    reorder.mutate(ids);
  };

  return (
    <>
      <PageHeading eyebrow="AUTOMATION" title={pageTitles[path]} description={pageDescriptions[path]}
        actions={canEdit && !editing ? <Button kind="primary" onClick={() => setEditing('new')} testId="button-new-rule">New rule</Button> : undefined} />
      {settings.data && !settings.data.enabled && <OffNotice canSwitch={canManage(role)} />}
      {editing && <RuleEditor key={editing === 'new' ? 'new' : editing.id} rule={editing === 'new' ? null : editing} first={page.first} onClose={() => setEditing(null)} />}

      <section className="panel auto-rules" data-testid="list-rules">
        {rules.isLoading ? <SkeletonRows rows={3} /> : shown.length === 0 ? (
          <EmptyState bare icon={Workflow} title="No rules here yet">
            {page.empty} {canEdit ? 'Choose New rule to make the first one.' : 'Owners, admins and managers can create rules.'}
          </EmptyState>
        ) : shown.map((rule) => {
          const index = all.indexOf(rule);
          return (
            <article className={`auto-rule ${rule.enabled ? '' : 'auto-rule-off'}`} key={rule.id} data-testid={`rule-${rule.id}`}>
              <Switch on={rule.enabled} onChange={() => toggle.mutate(rule)} label={`${rule.name} is ${rule.enabled ? 'on' : 'off'}`} disabled={!canEdit || toggle.isPending} testId={`switch-rule-${rule.id}`} />
              <div className="auto-rule-text">
                <b>{rule.name}</b>
                <p>{rule.summary}</p>
                <small>
                  {rule.run_count === 0 ? 'Has not run yet' : `Ran ${rule.run_count.toLocaleString()} ${rule.run_count === 1 ? 'time' : 'times'}${rule.last_run_at ? `, last ${timeAgo(rule.last_run_at)}` : ''}`}
                  {rule.failed_count > 0 && <span className="auto-bad"> · {rule.failed_count} failed</span>}
                  {rule.created_by_name ? ` · by ${rule.created_by_name}` : ''}
                </small>
              </div>
              {canEdit && (
                <div className="collab-actions">
                  {!page.kinds && all.length > 1 && (
                    <>
                      <button type="button" className="auto-icon" onClick={() => move(index, -1)} disabled={index === 0 || reorder.isPending} aria-label="Run earlier" data-testid={`rule-up-${rule.id}`}><ArrowUp size={16} /></button>
                      <button type="button" className="auto-icon" onClick={() => move(index, 1)} disabled={index === all.length - 1 || reorder.isPending} aria-label="Run later" data-testid={`rule-down-${rule.id}`}><ArrowDown size={16} /></button>
                    </>
                  )}
                  <Button onClick={() => setEditing(rule)}><Pencil size={14} /> Edit</Button>
                  <Button onClick={() => { if (confirm(`Delete the rule “${rule.name}”? Its history goes with it.`)) remove.mutate(rule.id); }} disabled={remove.isPending}><Trash2 size={14} /> Delete</Button>
                </div>
              )}
            </article>
          );
        })}
      </section>
      {!page.kinds && all.length > 1 && <p className="field-hint auto-order-hint">Rules run from top to bottom. When two rules set the same thing, the lower one has the last word.</p>}

      {path === '/automation' && canManage(role) && all.some((r) => r.enabled) && <RunOnRecent />}
      {canEdit && !editing && rules.data && <SuggestedRules existing={all} />}

      {path === '/automation' && (
        <>
          <div className="panel-head auto-history-head"><div><h2>What the rules did</h2><p>The most recent 50 runs. A run that fails is tried three times.</p></div></div>
          <section className="panel collab-list" data-testid="list-runs">
            {runs.isLoading ? <SkeletonRows rows={3} /> : !runs.data?.length
              ? <EmptyState bare icon={Workflow} title="Nothing has run yet">Each time a rule acts on a new email, what it did is recorded here.</EmptyState>
              : runs.data.map((run) => <RunRow key={run.id} run={run} />)}
          </section>
        </>
      )}
    </>
  );
}

/** Settings > Automation: the switch for the workspace and one for each mailbox. */
export function AutomationControls() {
  const client = useQueryClient();
  const toast = useToast();
  const { role } = useSession();
  const allowed = canManage(role);
  const settings = useQuery({ queryKey: ['automation', 'settings'], queryFn: api.automationSettings });
  const change = useMutation({
    mutationFn: (body: { enabled?: boolean; mailboxes?: Record<number, boolean> }) => api.updateAutomationSettings(body),
    onSuccess: (data) => { client.setQueryData(['automation', 'settings'], data); client.invalidateQueries({ queryKey: ['automation'] }); },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not change the setting.'),
  });
  const s = settings.data;
  return (
    <section className="panel settings-main auto-controls" data-testid="panel-automation-controls">
      {!s ? <SkeletonRows rows={2} /> : (
        <>
          <div className="auto-switch-row auto-switch-main">
            <div><b>Run rules on new mail</b><p>{s.enabled ? 'On. Rules act on each new email as it arrives.' : 'Off. Nothing happens on its own; rules stay saved for when you switch this on.'}</p></div>
            <Switch on={s.enabled} onChange={(on) => change.mutate({ enabled: on })} label="Run rules on new mail" disabled={!allowed || change.isPending} testId="switch-automation" />
          </div>
          {s.mailboxes.length > 0 && <h3>Mailboxes</h3>}
          {s.mailboxes.map((m) => (
            <div className="auto-switch-row" key={m.account_id}>
              <div><b>{m.email_address}</b><p>{!s.enabled ? 'Off, because automation is off for the workspace.' : m.enabled ? 'Rules run on mail arriving here.' : 'Rules skip this mailbox.'}</p></div>
              <Switch on={s.enabled && m.enabled} onChange={(on) => change.mutate({ mailboxes: { [m.account_id]: on } })} label={`Rules for ${m.email_address}`} disabled={!allowed || !s.enabled || change.isPending} testId={`switch-mailbox-${m.account_id}`} />
            </div>
          ))}
          <p className="field-hint">{allowed ? <>Rules themselves are made under <Link href="/automation" className="text-link">Automation rules</Link>.</> : 'Only owners and admins can change these switches.'}</p>
        </>
      )}
    </section>
  );
}

/** What exists in this product today. Shown on the Overview so nobody has to guess what is automatic. */
const CAPABILITIES: { name: string; detail: string; built: boolean }[] = [
  { name: 'Rules on new mail', detail: 'Add a label, set priority or status, assign to a person, share out in turn, flag, archive, notify.', built: true },
  { name: 'Conditions', detail: 'Mailbox, sender, recipient, subject, message text, attachments.', built: true },
  { name: 'Run history and retries', detail: 'Every run is recorded. One run per rule per email; a failed run is tried three times.', built: true },
  { name: 'On/off switches', detail: 'For the whole workspace, each mailbox and each rule. Off until you switch it on.', built: true },
  { name: 'AI summaries, priority and reply drafts', detail: 'New mail is summarised and given a Low, Medium or High priority; replies are drafted and wait for your approval. Needs a Gemini key and the AI switch.', built: true },
  { name: 'Write with AI', detail: 'Wherever you write an email, type a short instruction and the AI writes or rewrites it for you to check.', built: true },
  { name: 'AI sending replies on its own', detail: 'Off until you switch it on, separately for Low and Medium priority, with a daily limit. High priority always needs a person.', built: true },
  { name: 'Follow-up reminders and timed rules', detail: 'Remind yourself about a conversation, optionally only if nobody replies. Rules can act when an email has waited without an answer, and can use the AI’s priority.', built: true },
  { name: 'Analytics', detail: 'Mail per day, time to reply, what each rule and the AI did. See the Analytics page.', built: true },
  { name: 'Webhooks', detail: 'Not available yet.', built: false },
];

export function AutomationOverview() {
  const summary = useQuery({ queryKey: ['automation', 'summary'], queryFn: api.automationSummary, refetchInterval: 30000 });
  const s = summary.data;
  return (
    <section className="panel overview-panel auto-overview" data-testid="panel-automations">
      <div className="panel-head">
        <div>
          <h2>Automations {s && <span className={`ol-chip auto-state ${s.enabled ? 'auto-state-on' : 'auto-state-off'}`} data-testid="text-automation-state">{s.enabled ? 'On' : 'Off'}</span>}</h2>
          <p>{!s ? 'Loading…' : s.rules_total === 0 ? 'No rules have been made yet.'
            : `${s.rules_on} of ${s.rules_total} ${s.rules_total === 1 ? 'rule' : 'rules'} on · ${s.runs_today.toLocaleString()} ${s.runs_today === 1 ? 'run' : 'runs'} in the last 24 hours${s.failed_today ? ` · ${s.failed_today} failed` : ''}`}</p>
        </div>
        <Link href="/automation" className="activity-link">Manage rules <ArrowRight size={16} /></Link>
      </div>
      <div className="auto-overview-grid">
        <div>
          <h3>Your rules</h3>
          {!s ? <SkeletonRows rows={2} /> : s.rules.length === 0
            ? <p className="auto-none">Nothing is automatic in this workspace yet. <Link href="/automation" className="text-link">Make a rule</Link></p>
            : (
              <ul className="auto-mini" data-testid="list-overview-rules">
                {s.rules.map((rule) => (
                  <li key={rule.id}>
                    <i className={`ol-status-dot ${rule.enabled && s.enabled ? 'ol-status-open' : 'ol-status-closed'}`} aria-hidden />
                    <span><b>{rule.name}</b><small>{rule.summary}</small></span>
                    <em>{!rule.enabled ? 'Off' : rule.run_count === 0 ? 'Not run yet' : `${rule.run_count.toLocaleString()} ${rule.run_count === 1 ? 'run' : 'runs'}`}{rule.failed_count > 0 && <span className="auto-bad"> · {rule.failed_count} failed</span>}</em>
                  </li>
                ))}
              </ul>
            )}
          {s && s.recent.length > 0 && (
            <>
              <h3>Latest</h3>
              <ul className="auto-mini auto-mini-runs">
                {s.recent.slice(0, 4).map((run) => (
                  <li key={run.id}>
                    <i className={`ol-status-dot ${run.status === 'done' ? 'ol-status-open' : 'ol-status-pending'}`} aria-hidden />
                    <span><b>{run.rule_name}</b><small>{run.status === 'done' ? run.done.join(' · ') : `Failed: ${run.error}`}</small></span>
                    <em>{timeAgo(run.created_at)}</em>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
        <div>
          <h3>What automation can do</h3>
          <ul className="auto-caps" data-testid="list-capabilities">
            {CAPABILITIES.map((c) => (
              <li key={c.name} className={c.built ? 'auto-cap-built' : 'auto-cap-later'}>
                {c.built ? <CheckCircle2 size={17} /> : <CircleSlash size={17} />}
                <span><b>{c.name}</b><small>{c.detail}</small></span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
