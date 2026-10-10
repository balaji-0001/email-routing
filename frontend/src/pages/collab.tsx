// Contacts, templates, notifications and the list of recent internal notes.
import { useState, type FormEvent } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'wouter';
import { AlarmClock, AtSign, Bell, ContactRound, FileText, Mail, Pencil, Search, StickyNote, Trash2, UserRound, Workflow } from 'lucide-react';
import { Avatar, Button, EmptyState, PageHeading, SkeletonRows, Switch, useToast } from '@/components/kit';
import { pageDescriptions } from '@/data';
import { AiWriter } from './ai';
import { api, ApiError, type AppNotification, type Template } from '@/lib/api';
import { dateTime, timeAgo } from '@/lib/format';
import { canManage, useSession } from '@/lib/session';

const PAGE = 50;

export function ContactsPage() {
  const [text, setText] = useState('');
  const [search, setSearch] = useState('');
  const list = useInfiniteQuery({
    queryKey: ['contacts', search],
    queryFn: ({ pageParam }) => api.contacts({ search, limit: PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (last.length === PAGE ? pages.length * PAGE : undefined),
  });
  const people = list.data?.pages.flat() ?? [];
  return (
    <>
      <PageHeading eyebrow="ORGANIZE" title="Contacts" description={pageDescriptions['/contacts']} />
      <form className="search-wide" role="search" onSubmit={(e: FormEvent) => { e.preventDefault(); setSearch(text.trim()); }}>
        <Search size={21} />
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Find a person by name or address…" aria-label="Search contacts" data-testid="input-contact-search" />
      </form>
      <section className="panel table-panel" style={{ marginTop: '1rem' }}>
        {list.isLoading ? <SkeletonRows rows={5} /> : people.length === 0 ? (
          <EmptyState icon={ContactRound} title={search ? `Nobody matches “${search}”` : 'No contacts yet'}>
            {search ? 'Try part of a name or an email address.' : 'People your team receives mail from or writes to are gathered here automatically.'}
          </EmptyState>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table collab-table">
              <thead><tr><th>Person</th><th>Received</th><th>Sent</th><th>Last message</th><th /></tr></thead>
              <tbody>
                {people.map((person) => (
                  <tr key={person.email} data-testid={`contact-${person.email}`}>
                    <td><div className="table-person"><Avatar name={person.name || person.email} /><span><b>{person.name || person.email}</b><small>{person.email}</small></span></div></td>
                    <td>{person.received.toLocaleString()}</td>
                    <td>{person.sent.toLocaleString()}</td>
                    <td>{person.last_message_at ? timeAgo(person.last_message_at) : '–'}</td>
                    <td>
                      <div className="collab-actions">
                        <Link href={`/search?q=${encodeURIComponent(person.email)}`} className="button button-secondary"><Mail size={14} /> Their mail</Link>
                        <Link href={`/compose?to=${encodeURIComponent(person.email)}`} className="button button-secondary"><Pencil size={14} /> Write</Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {list.hasNextPage && <div className="ol-more"><Button onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage} testId="button-more-contacts">{list.isFetchingNextPage ? 'Loading…' : 'Load more'}</Button></div>}
          </div>
        )}
      </section>
    </>
  );
}

const BLANK = { name: '', subject: '', body: '' };

export function TemplatesPage() {
  const client = useQueryClient();
  const toast = useToast();
  const { role } = useSession();
  const canEdit = canManage(role) || role === 'manager';
  const templates = useQuery({ queryKey: ['templates'], queryFn: api.templates });
  const [editing, setEditing] = useState<Template | 'new' | null>(null);
  const [form, setForm] = useState(BLANK);
  const [error, setError] = useState<string | null>(null);

  function open(target: Template | 'new') {
    setEditing(target);
    setError(null);
    setForm(target === 'new' ? BLANK : { name: target.name, subject: target.subject, body: target.body });
  }
  const done = (message: string) => () => { client.invalidateQueries({ queryKey: ['templates'] }); setEditing(null); toast(message); };
  const save = useMutation({
    mutationFn: () => (editing === 'new' || editing === null ? api.createTemplate(form) : api.updateTemplate(editing.id, form)),
    onSuccess: done('Template saved.'),
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Could not save the template.'),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteTemplate(id),
    onSuccess: done('Template deleted.'),
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not delete the template.'),
  });

  return (
    <>
      <PageHeading eyebrow="ORGANIZE" title="Templates" description={pageDescriptions['/templates']}
        actions={canEdit && !editing ? <Button kind="primary" onClick={() => open('new')} testId="button-new-template">New template</Button> : undefined} />
      {editing && (
        <form className="panel settings-main collab-form" onSubmit={(e) => { e.preventDefault(); setError(null); save.mutate(); }} data-testid="form-template">
          {error && <div className="form-error" role="alert">{error}</div>}
          <label className="field"><span>Name</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={120} placeholder="Refund approved" autoFocus data-testid="input-template-name" /></label>
          <label className="field"><span>Subject (optional)</span><input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} maxLength={500} data-testid="input-template-subject" /></label>
          <AiWriter current={form.body} onResult={(r) => setForm((f) => ({ ...f, body: r.body, subject: f.subject || r.subject }))} />
          <label className="field"><span>Message</span>
            <textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} rows={9} data-testid="input-template-body" />
          </label>
          <p className="field-hint">Use <code>{'{{recipient_name}}'}</code> for the person you are writing to and <code>{'{{my_name}}'}</code> for your own name. They are filled in when the template is used.</p>
          <div className="settings-form-footer">
            <span />
            <div className="collab-actions">
              <Button onClick={() => setEditing(null)}>Cancel</Button>
              <Button kind="primary" type="submit" disabled={!form.name.trim() || !form.body.trim() || save.isPending} testId="button-save-template">{save.isPending ? 'Saving…' : 'Save template'}</Button>
            </div>
          </div>
        </form>
      )}
      <section className="panel table-panel" style={{ marginTop: '1rem' }}>
        {templates.isLoading ? <SkeletonRows rows={3} /> : !templates.data?.length ? (
          <EmptyState icon={FileText} title="No templates yet">
            {canEdit ? 'Save a reply you write often, then insert it from the Templates button when composing.' : 'Owners, admins and managers can create templates. Once there are some, use them from the Templates button when composing.'}
          </EmptyState>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table collab-table">
              <thead><tr><th>Template</th><th>Starts with</th><th>Updated</th><th /></tr></thead>
              <tbody>
                {templates.data.map((template) => (
                  <tr key={template.id} data-testid={`template-${template.id}`}>
                    <td><div className="table-person"><span><b>{template.name}</b><small>{template.subject || 'No subject'}</small></span></div></td>
                    <td className="collab-preview">{template.body.trim().split('\n')[0]}</td>
                    <td>{timeAgo(template.updated_at)}{template.created_by_name ? ` · ${template.created_by_name}` : ''}</td>
                    <td>
                      {canEdit && (
                        <div className="collab-actions">
                          <Button onClick={() => open(template)}><Pencil size={14} /> Edit</Button>
                          <Button onClick={() => { if (confirm(`Delete the template “${template.name}”?`)) remove.mutate(template.id); }} disabled={remove.isPending}><Trash2 size={14} /> Delete</Button>
                        </div>
                      )}
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

const KIND_ICON = { assigned: UserRound, mentioned: AtSign, note: StickyNote, rule: Workflow, reminder: AlarmClock };

export function NotificationsPage() {
  const client = useQueryClient();
  const list = useQuery({ queryKey: ['notifications'], queryFn: api.notifications, refetchInterval: 20000 });
  const read = useMutation({ mutationFn: (ids: number[]) => api.markNotificationsRead(ids), onSuccess: () => client.invalidateQueries({ queryKey: ['notifications'] }) });
  const items = list.data?.items ?? [];
  const row = (n: AppNotification) => {
    const Icon = KIND_ICON[n.kind] ?? Bell;
    const inner = (
      <>
        <span className="collab-note-icon"><Icon size={17} /></span>
        <span className="collab-note-text"><b>{n.title}</b>{n.body && <small>{n.body}</small>}<time>{timeAgo(n.created_at)}</time></span>
        {!n.is_read && <i className="collab-unread" aria-label="Unread" />}
      </>
    );
    return n.conversation_id
      ? <Link key={n.id} href={`/inbox?c=${n.conversation_id}`} className={`collab-notification ${n.is_read ? '' : 'unread'}`} onClick={() => { if (!n.is_read) read.mutate([n.id]); }} data-testid={`notification-${n.id}`}>{inner}</Link>
      : <div key={n.id} className={`collab-notification ${n.is_read ? '' : 'unread'}`} data-testid={`notification-${n.id}`}>{inner}</div>;
  };
  return (
    <>
      <PageHeading eyebrow="ORGANIZE" title="Notifications" description="Assignments, mentions and notes meant for you."
        actions={list.data?.unread ? <Button onClick={() => read.mutate([])} disabled={read.isPending} testId="button-read-all">Mark all as read</Button> : undefined} />
      <section className="panel collab-list" data-testid="list-notifications">
        {list.isLoading ? <SkeletonRows rows={4} /> : items.length === 0 ? (
          <EmptyState icon={Bell} title="Nothing new">You are told here when a conversation is assigned to you, when someone mentions you in a note, and when a note is left on a conversation of yours.</EmptyState>
        ) : items.map(row)}
      </section>
    </>
  );
}

/** Settings > Profile: whether this person's notifications also go to their email address. */
export function EmailNotificationsPanel() {
  const client = useQueryClient();
  const toast = useToast();
  const preference = useQuery({ queryKey: ['email-preference'], queryFn: api.emailPreference });
  const change = useMutation({
    mutationFn: (enabled: boolean) => api.setEmailPreference(enabled),
    onSuccess: (data) => client.setQueryData(['email-preference'], data),
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not change the setting.'),
  });
  const p = preference.data;
  if (!p) return null;
  return (
    <section className="panel settings-main appearance-panel" data-testid="panel-email-notifications">
      <div>
        <h2>Email me my notifications</h2>
        <p>{!p.available ? 'Email is not set up on this server yet, so notifications appear only in the app.'
          : p.enabled ? `On. Assignments, mentions, reminders and rule alerts are also sent to ${p.address}, unless you have already read them here.`
          : 'Off. Notifications appear only in the app.'}</p>
      </div>
      <Switch on={p.available && p.enabled} onChange={(on) => change.mutate(on)} label="Email me my notifications" disabled={!p.available || change.isPending} testId="switch-email-notifications" />
    </section>
  );
}

export function NotesPage() {
  const notes = useQuery({ queryKey: ['recent-notes'], queryFn: api.recentNotes });
  return (
    <>
      <PageHeading eyebrow="COLLABORATE" title="Internal notes" description={pageDescriptions['/internal-notes']} />
      <section className="panel collab-list" data-testid="list-notes">
        {notes.isLoading ? <SkeletonRows rows={4} /> : !notes.data?.length ? (
          <EmptyState icon={StickyNote} title="No internal notes yet">Open a conversation and add a note under it. Notes from every conversation you can see are gathered here, newest first.</EmptyState>
        ) : notes.data.map((note) => (
          <Link key={note.id} href={`/inbox?c=${note.conversation_id}`} className="collab-notification" data-testid={`recent-note-${note.id}`}>
            <Avatar name={note.author_name ?? '?'} />
            <span className="collab-note-text"><b>{note.author_name ?? 'Someone'} <em>on {note.conversation_subject}</em></b><small>{note.body}</small><time title={dateTime(note.created_at)}>{timeAgo(note.created_at)}</time></span>
          </Link>
        ))}
      </section>
    </>
  );
}
