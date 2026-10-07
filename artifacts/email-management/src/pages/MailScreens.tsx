import { useMemo, useState } from 'react';
import { Link, useLocation } from 'wouter';
import {
  AlignLeft, Archive, ArrowDownUp, ArrowLeft, ArrowRight, Bold, CalendarClock,
  CalendarDays, Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight,
  Download, Ellipsis, FileText, Filter, Forward, Inbox, Italic, Link2, MailOpen,
  Paperclip, Plus, Reply, RefreshCw, Search, Send, ShieldCheck, Smile, Sparkles,
  Star, StickyNote, Trash, X, Zap,
} from 'lucide-react';
import { accounts, mails, team, type Mail as MailData } from '../data';
import { Button, PageHeading, Toast } from '../components/prototype-ui';

const providerClass = (provider: string) =>
  provider === 'Gmail' ? 'gmail' : provider === 'IMAP' ? 'imap' : 'outlook';
const providerInitial = (provider: string) =>
  provider === 'Gmail' ? 'G' : provider === 'IMAP' ? 'I' : 'M';
const initials = (name: string) => name.split(' ').map((part) => part[0]).join('');

export function Mailbox({ path }: { path: string }) {
  const [, navigate] = useLocation();
  const [query, setQuery] = useState(
    new URLSearchParams(location.search).get('q') ||
      sessionStorage.getItem('northstar-search-query') ||
      '',
  );
  const [filter, setFilter] = useState('All mail');
  const [sort, setSort] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [toast, setToast] = useState('');
  const [confirm, setConfirm] = useState('');
  const [filterOpen, setFilterOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const titleMap: Record<string, string> = {
    '/inbox': 'Unified inbox',
    '/drafts': 'Drafts',
    '/sent': 'Sent',
    '/starred': 'Starred',
    '/archive': 'Archive',
    '/trash': 'Trash',
    '/search': 'Search',
  };
  let rows = [...mails];
  if (path === '/starred') rows = rows.filter((mail) => mail.star);
  if (path === '/trash') rows = rows.slice(2, 4);
  if (path === '/archive') rows = rows.slice(3);
  if (path === '/drafts') rows = rows.slice(1, 4);
  if (path === '/sent') rows = rows.slice(4, 8);
  rows = rows.filter((mail) =>
    `${mail.sender} ${mail.subject} ${mail.preview} ${mail.email}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  if (filter === 'Unread') rows = rows.filter((mail) => mail.unread);
  if (filter === 'High priority') rows = rows.filter((mail) => mail.priority === 'High');
  if (sort) rows.reverse();

  const setBulkAction = (action: string) => {
    setConfirm('');
    setSelected([]);
    setToast(`${action} — preview only. No email data was changed.`);
  };
  const changeFilter = (value: string) => {
    setFilter(value);
    setFilterOpen(false);
  };

  return (
    <>
      <PageHeading
        eyebrow={path === '/inbox' ? 'SHARED INBOX' : 'MAIL'}
        title={titleMap[path]}
        description={path === '/search'
          ? 'Search across every connected inbox and shared conversation.'
          : 'Work through conversations with your team, all in one place.'}
        actions={<Button kind="primary" onClick={() => navigate('/compose')} testId="button-compose-mail"><Plus size={15} />Compose</Button>}
      />
      {path === '/search' && (
        <label className="search-wide">
          <Search size={18} />
          <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search people, subjects, messages…" data-testid="input-mail-search" />
          <span>⌘ K</span>
        </label>
      )}
      <div className="mailbox-toolbar">
        <div className="toolbar-left">
          <button
            type="button"
            className="select-control"
            aria-label="Select all conversations"
            aria-pressed={selected.length === rows.length && rows.length > 0}
            onClick={() => setSelected(selected.length === rows.length ? [] : rows.map((mail) => mail.id))}
            data-testid="button-select-all"
          >
            <span className={`checkbox ${selected.length === rows.length && rows.length ? 'checked' : ''}`}>
              {selected.length === rows.length && rows.length ? <Check size={12} /> : null}
            </span>
            <ChevronDown size={13} />
          </button>
          <button
            type="button"
            className={`icon-button ${refreshing ? 'is-refreshing' : ''}`}
            aria-label="Refresh inbox preview"
            onClick={() => {
              setRefreshing(true);
              window.setTimeout(() => setRefreshing(false), 450);
              setToast('Preview refreshed. Account data is static in this demo.');
            }}
            data-testid="button-refresh-inbox"
          ><RefreshCw size={15} /></button>
          <div className="popover-anchor">
            <button
              type="button"
              className={`icon-button ${filterOpen ? 'active' : ''}`}
              aria-label="Filter conversations"
              aria-expanded={filterOpen}
              onClick={() => setFilterOpen(!filterOpen)}
              data-testid="button-filter-conversations"
            ><Filter size={15} /></button>
            {filterOpen && (
              <div className="shell-popover filter-popover" role="menu" aria-label="Conversation filters">
                {['All mail', 'Unread', 'High priority'].map((option) => (
                  <button
                    type="button"
                    role="menuitemradio"
                    aria-checked={filter === option}
                    key={option}
                    onClick={() => changeFilter(option)}
                    data-testid={`filter-option-${option.toLowerCase().replaceAll(' ', '-')}`}
                  >{option}{filter === option && <Check size={13} />}</button>
                ))}
              </div>
            )}
          </div>
          <select value={filter} onChange={(event) => changeFilter(event.target.value)} aria-label="Filter conversations" data-testid="select-mail-filter">
            <option>All mail</option><option>Unread</option><option>High priority</option>
          </select>
          {selected.length > 0 && (
            <div className="bulk-actions">
              <span>{selected.length} selected</span>
              <button type="button" onClick={() => setConfirm('Archive selected conversations?')} aria-label="Archive selected" data-testid="button-bulk-archive"><Archive size={15} /></button>
              <button type="button" onClick={() => setConfirm('Mark selected as read?')} aria-label="Mark selected read" data-testid="button-bulk-read"><MailOpen size={15} /></button>
              <button type="button" onClick={() => setConfirm('Delete selected conversations?')} aria-label="Delete selected" data-testid="button-bulk-delete"><Trash size={15} /></button>
            </div>
          )}
        </div>
        <button
          type="button"
          className={`sort-button ${sort ? 'sort-active' : ''}`}
          onClick={() => { setSort(!sort); setToast(sort ? 'Newest conversations shown first.' : 'Oldest conversations shown first.'); }}
          aria-label="Toggle conversation sort order"
          data-testid="button-sort-conversations"
        ><ArrowDownUp size={14} /> {sort ? 'Oldest first' : 'Newest first'} <ChevronDown size={13} /></button>
      </div>

      <div className="mail-layout">
        <section className="panel mail-list-panel">
          <div className="mail-list-head">
            <span>{rows.length} conversations</span>
            <span className="mail-list-accounts"><i style={{ background: '#d65345' }} /><i style={{ background: '#3378c8' }} /><i style={{ background: '#6370b4' }} /> All accounts</span>
          </div>
          {rows.length
            ? rows.map((mail) => (
              <MailRow
                key={mail.id}
                mail={mail}
                selected={selected.includes(mail.id)}
                onSelect={() => setSelected(selected.includes(mail.id) ? selected.filter((id) => id !== mail.id) : [...selected, mail.id])}
                onNotice={setToast}
              />
            ))
            : (
              <div className="empty-state">
                <div className="empty-icon"><Search size={21} /></div>
                <h3>No conversations found</h3>
                <p>Try a different search or adjust your filters.</p>
                <button type="button" className="text-link" onClick={() => { setQuery(''); changeFilter('All mail'); }} data-testid="button-clear-mail-filters">Clear filters</button>
              </div>
            )}
        </section>
        <aside className="inbox-aside">
          <div className="panel inbox-summary">
            <div className="aside-title"><div><h3>Inbox health</h3><p>Across all accounts</p></div><Inbox size={16} /></div>
            <div className="health-score"><strong>98</strong><span>/ 100</span><b>Healthy</b></div>
            <div className="health-line"><span /></div>
            <div className="aside-stat"><span>Last sync</span><b>Just now</b></div>
            <div className="aside-stat"><span>Open threads</span><b>38</b></div>
            <div className="aside-stat"><span>Unassigned</span><b>6</b></div>
          </div>
          <div className="panel ai-aside">
            <span className="ai-kicker"><Sparkles size={14} /> ASSISTED INSIGHT</span>
            <h3>One quick win</h3>
            <p>Two high-priority messages are waiting for a first reply. Start with Owen’s access issue.</p>
            <Link href="/email/m-1047" className="text-link" data-testid="link-attention-thread">Open conversation <ArrowRight size={14} /></Link>
            <div className="ai-disclaimer">Suggestions are illustrative in this UI preview.</div>
          </div>
          <div className="panel team-aside">
            <div className="aside-title"><div><h3>On your team</h3><p>4 members active today</p></div><Link href="/team" className="text-link" data-testid="link-inbox-team">All</Link></div>
            <div className="team-face-row">{team.map((member) => <span key={member.email} className={`avatar avatar-${member.tone}`} title={member.name}>{member.initials}</span>)}<Link href="/team/invite" className="add-face" aria-label="Invite teammate" data-testid="link-invite-from-inbox"><Plus size={14} /></Link></div>
            <div className="team-aside-note"><span className="sync-dot" /> 3 teammates online</div>
          </div>
        </aside>
      </div>

      {confirm && (
        <div className="modal-backdrop">
          <div className="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="bulk-confirm-heading">
            <div className="modal-icon"><ShieldCheck size={19} /></div>
            <h3 id="bulk-confirm-heading">{confirm}</h3>
            <p>This prototype won’t modify connected mail. You can safely preview this action.</p>
            <div className="modal-actions">
              <Button onClick={() => setConfirm('')} testId="button-cancel-bulk-action">Cancel</Button>
              <Button kind="primary" onClick={() => setBulkAction(confirm.replace('?', ''))} testId="button-confirm-bulk-action">Confirm preview</Button>
            </div>
          </div>
        </div>
      )}
      <Toast message={toast} close={() => setToast('')} />
    </>
  );
}

export function MailRow({
  mail,
  compact = false,
  selected = false,
  onSelect,
  onNotice,
}: {
  mail: MailData;
  compact?: boolean;
  selected?: boolean;
  onSelect?: () => void;
  onNotice: (message: string) => void;
}) {
  const [starred, setStarred] = useState(mail.star);
  return (
    <div className={`mail-row ${mail.unread ? 'unread' : ''} ${compact ? 'compact' : ''} ${selected ? 'selected' : ''}`} data-testid={`row-conversation-${mail.id}`}>
      <button
        type="button"
        className={`checkbox ${selected ? 'checked' : ''}`}
        aria-label={`Select ${mail.subject}`}
        aria-pressed={selected}
        onClick={onSelect || (() => onNotice('Conversation selection is available in the inbox view.'))}
        data-testid={`checkbox-mail-${mail.id}`}
      >{selected && <Check size={12} />}</button>
      <button
        type="button"
        className={`star-button ${starred ? 'is-starred' : ''}`}
        onClick={() => { setStarred(!starred); onNotice(starred ? 'Star removed locally.' : 'Conversation starred locally.'); }}
        aria-label={starred ? 'Remove star' : 'Star conversation'}
        aria-pressed={starred}
        data-testid={`button-star-${mail.id}`}
      ><Star size={15} fill={starred ? 'currentColor' : 'none'} /></button>
      <span className={`provider-dot ${providerClass(mail.provider)}`} title={`${mail.provider} · ${mail.account}`}>{providerInitial(mail.provider)}</span>
      <Link href={`/email/${mail.id}`} className="mail-row-content" data-testid={`link-conversation-${mail.id}`}>
        <div className="mail-row-main"><b className="mail-sender">{mail.sender}</b><span className="mail-address">{mail.email}</span><span className="mail-time">{mail.time}</span></div>
        <div className="mail-subject-line"><span className="mail-subject">{mail.subject}</span>{mail.priority === 'High' && <span className="priority-mark"><Zap size={12} /> High</span>}{mail.attachment && <Paperclip size={13} className="attachment-icon" />}</div>
        <div className="mail-preview">{mail.preview}</div>
        <div className="mail-row-meta">
          {mail.labels.map((label) => <span className={`label-chip label-${label.toLowerCase().replaceAll(' ', '-')}`} key={label}>{label}</span>)}
          <span className="assignment-meta"><span className={`avatar avatar-${mail.assigned === 'Alex Morgan' ? 'blue' : mail.assigned === 'Priya Shah' ? 'peach' : 'mint'}`}>{mail.assigned === 'Unassigned' ? '–' : initials(mail.assigned)}</span>{mail.assigned}</span>
        </div>
      </Link>
    </div>
  );
}

export function EmailDetail({ id }: { id: string }) {
  const [, navigate] = useLocation();
  const mail = mails.find((item) => item.id === id) || mails[0];
  const mailIndex = mails.findIndex((item) => item.id === mail.id);
  const [replyMode, setReplyMode] = useState<'reply' | 'forward' | null>(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [toast, setToast] = useState('');
  const [assignee, setAssignee] = useState(mail.assigned);
  const [labels, setLabels] = useState(mail.labels);
  const related = mails.filter((item) => item.id !== mail.id && item.sender !== mail.sender).slice(0, 2);
  const move = (offset: number) => {
    const next = mails[(mailIndex + offset + mails.length) % mails.length];
    navigate(`/email/${next.id}`);
  };

  return (
    <>
      <div className="detail-breadcrumb">
        <Link href="/inbox" data-testid="link-back-inbox"><ArrowLeft size={15} /> Back to inbox</Link>
        <div>
          <button type="button" className="icon-button" aria-label="Previous conversation" onClick={() => move(-1)} data-testid="button-previous-thread"><ChevronLeft size={17} /></button>
          <button type="button" className="icon-button" aria-label="Next conversation" onClick={() => move(1)} data-testid="button-next-thread"><ChevronRight size={17} /></button>
        </div>
      </div>
      <div className="detail-layout">
        <section className="panel detail-main">
          <div className="detail-toolbar">
            <div className="toolbar-left">
              <button type="button" className="icon-button" aria-label="Archive conversation" onClick={() => setToast('Archive is a UI-only preview action.')} data-testid="button-archive-thread"><Archive size={16} /></button>
              <button type="button" className="icon-button" aria-label="Delete conversation" onClick={() => setToast('Delete is a UI-only preview action.')} data-testid="button-delete-thread"><Trash size={16} /></button>
              <button type="button" className="icon-button" aria-label="Mark conversation unread" onClick={() => setToast('Unread state is illustrative in this preview.')} data-testid="button-unread-thread"><MailOpen size={16} /></button>
              <span className="toolbar-divider" />
              <div className="popover-anchor">
                <button type="button" className="icon-button" aria-label="More conversation actions" aria-expanded={moreOpen} onClick={() => setMoreOpen(!moreOpen)} data-testid="button-thread-more"><Ellipsis size={18} /></button>
                {moreOpen && <div className="shell-popover" role="menu">
                  <button type="button" onClick={() => { setMoreOpen(false); setToast('Conversation link copied in this local preview.'); }}>Copy conversation link</button>
                  <button type="button" onClick={() => { setMoreOpen(false); setToast('Print view is not available in this preview.'); }}>Print conversation</button>
                </div>}
              </div>
            </div>
            <Button icon={ArrowLeft} onClick={() => navigate('/inbox')} testId="button-thread-back">Back</Button>
          </div>
          <div className="thread-head">
            <div className="thread-tags">{labels.map((label) => <span className="label-chip" key={label}>{label}</span>)}<span className="priority-mark"><Zap size={12} />{mail.priority} priority</span></div>
            <h1>{mail.subject}</h1>
            <div className="thread-account"><span className={`provider-dot ${providerClass(mail.provider)}`}>{providerInitial(mail.provider)}</span> via {mail.account}</div>
          </div>
          <article className="message-card">
            <div className="message-head">
              <span className="avatar avatar-peach">{initials(mail.sender)}</span>
              <div className="message-from"><b>{mail.sender}</b><span>&lt;{mail.email}&gt;</span><small>To: Alex Morgan · hello@northstar.studio</small></div>
              <time>{mail.time} · Jun 17</time>
              <button type="button" className="icon-button" aria-label="Message options" onClick={() => setToast('Message options are UI-only in this preview.')} data-testid="button-message-options"><Ellipsis size={17} /></button>
            </div>
            <div className="message-body">
              <p>Hi Alex,</p><p>{mail.preview.replace('…', '.')}</p>
              <p>I’ve included a little more context below. Let me know if you’d like anything else from our side before we move forward.</p>
              <p>Thanks,<br />{mail.sender.split(' ')[0]}</p>
            </div>
            {mail.attachment && <div className="attachment-card">
              <span className="file-icon"><FileText size={18} /></span>
              <span><b>{mail.attachment}</b><small>PDF document · 2.4 MB</small></span>
              <button type="button" className="icon-button" aria-label={`Preview ${mail.attachment}`} onClick={() => setToast('Attachment preview requires a connected mail service.')} data-testid="button-preview-attachment"><Download size={16} /></button>
            </div>}
          </article>
          <div className="thread-actions">
            <Button kind="primary" icon={Reply} onClick={() => setReplyMode(replyMode === 'reply' ? null : 'reply')} testId="button-reply-thread">Reply</Button>
            <Button icon={Forward} onClick={() => setReplyMode(replyMode === 'forward' ? null : 'forward')} testId="button-forward-thread">Forward</Button>
            <Button icon={StickyNote} onClick={() => setNoteOpen(!noteOpen)} testId="button-add-internal-note">Add internal note</Button>
          </div>
          {replyMode && <div className="inline-reply">
            <div className="reply-to">{replyMode === 'reply' ? <Reply size={14} /> : <Forward size={14} />}{replyMode === 'reply' ? ` Replying to ${mail.sender}` : ` Forwarding to a teammate`}<ChevronDown size={13} /></div>
            <div className="reply-fields"><label>To<input defaultValue={replyMode === 'reply' ? mail.email : ''} placeholder="Add recipients" aria-label="Reply recipients" data-testid="input-thread-recipients" /></label><label>Cc / Bcc<input placeholder="Add Cc or Bcc recipients" aria-label="Cc and Bcc recipients" data-testid="input-thread-cc-bcc" /></label></div>
            <textarea placeholder={replyMode === 'reply' ? 'Write a reply…' : 'Add a note before forwarding…'} aria-label={replyMode === 'reply' ? 'Reply message' : 'Forward message'} data-testid="textarea-reply" />
            <div className="reply-bottom"><span>From: hello@northstar.studio</span><Button kind="primary" icon={Send} onClick={() => setToast('Sending is disabled. Connect a sending service to send real email.')} testId="button-send-reply">{replyMode === 'reply' ? 'Send reply' : 'Forward'}</Button></div>
          </div>}
          {noteOpen && <div className="inline-reply note-reply">
            <div className="reply-to"><StickyNote size={14} /> Private note for your team</div>
            <textarea placeholder="Add context only your team can see…" aria-label="Internal note" data-testid="textarea-note" />
            <div className="reply-bottom"><span>Only visible to Northstar Studio</span><Button kind="primary" onClick={() => { setNoteOpen(false); setToast('Note added locally for this preview session.'); }} testId="button-save-note">Add note</Button></div>
          </div>}
          <div className="thread-history"><span className="history-line" /><span>Earlier in this conversation · Jun 14</span><div className="history-preview"><span className="avatar avatar-blue">AM</span><div><b>Alex Morgan</b><small>Thanks for sending this over. We’ll review with the team and come back to you tomorrow…</small></div><button type="button" className="icon-button" aria-label="Expand earlier message" onClick={() => setToast('Earlier message expanded in this local preview.')} data-testid="button-expand-history"><ChevronDown size={15} /></button></div></div>
        </section>
        <aside className="detail-aside">
          <div className="panel detail-side-panel">
            <div className="side-panel-title"><h3>Conversation details</h3><button type="button" className="icon-button" aria-label="Conversation detail options" onClick={() => setToast('Conversation details are managed locally in this preview.')} data-testid="button-detail-options"><Ellipsis size={17} /></button></div>
            <DetailField label="Assigned to"><select value={assignee} aria-label="Assigned teammate" onChange={(event) => { setAssignee(event.target.value); setToast(`Assigned to ${event.target.value} locally.`); }} data-testid="select-thread-assignee"><option>Unassigned</option>{team.map((member) => <option key={member.email}>{member.name}</option>)}</select></DetailField>
            <DetailField label="Priority"><span className={`priority-pill ${mail.priority.toLowerCase()}`}><i />{mail.priority}</span></DetailField>
            <DetailField label="Sentiment"><span className="sentiment-pill"><Smile size={14} />{mail.sentiment}</span></DetailField>
            <DetailField label="Labels"><div className="label-line">{labels.map((label) => <button key={label} type="button" className="label-chip" onClick={() => { setLabels(labels.filter((item) => item !== label)); setToast(`${label} label removed locally.`); }}>{label}<X size={10} /></button>)}<button type="button" className="tiny-add" aria-label="Add label" onClick={() => { setLabels([...labels, 'Follow up']); setToast('Follow up label added locally.'); }} data-testid="button-add-label"><Plus size={13} /></button></div></DetailField>
            <DetailField label="Participants"><span>{mail.sender}<small>{mail.email}</small></span></DetailField>
            <DetailField label="Account"><span>{mail.account}<small>{mail.provider}</small></span></DetailField>
          </div>
          <div className="panel ai-summary-card"><span className="ai-kicker"><Sparkles size={13} /> AI SUMMARY · PREVIEW</span><p>{mail.summary}</p><button type="button" className="text-link" onClick={() => setToast('AI actions are illustrative only. No model is connected.')} data-testid="button-ai-reply-suggestion">Draft a reply <ArrowRight size={13} /></button><div className="ai-disclaimer">Suggested content needs human review.</div></div>
          <div className="panel detail-side-panel"><div className="side-panel-title"><h3>Related conversations</h3><span className="count-badge">{related.length}</span></div>{related.map((item) => <Link href={`/email/${item.id}`} className="related-item" key={item.id} data-testid={`link-related-${item.id}`}><span className="related-mark" /><span><b>{item.subject}</b><small>{item.sender} · {item.time}</small></span><ChevronRight size={14} /></Link>)}</div>
          <div className="panel activity-mini"><div className="side-panel-title"><h3>Activity</h3><button type="button" className="icon-button" aria-label="Activity details" onClick={() => setToast('Activity history is sample data.')} data-testid="button-thread-activity"><Ellipsis size={16} /></button></div><ActivityLine initials="AM" tone="blue" text="Alex Morgan opened this" time="2 min ago" /><ActivityLine initials="PS" tone="peach" text="Priya Shah assigned to Alex" time="4 min ago" /></div>
        </aside>
      </div>
      <Toast message={toast} close={() => setToast('')} />
    </>
  );
}

function ActivityLine({ initials: personInitials, tone, text, time }: { initials: string; tone: string; text: string; time: string }) {
  return <div className="activity-item"><span className={`avatar avatar-${tone}`}>{personInitials}</span><div className="activity-text"><p>{text}</p><small>{time}</small></div></div>;
}
function DetailField({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="detail-field"><span>{label}</span><div>{children}</div></div>;
}

export function Compose() {
  const [toast, setToast] = useState('');
  const [cc, setCc] = useState(false);
  const [bcc, setBcc] = useState(false);
  const [schedule, setSchedule] = useState(false);
  const [linkEditor, setLinkEditor] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');
  const [from, setFrom] = useState(accounts[0].address);
  const [bold, setBold] = useState(false);
  const [italic, setItalic] = useState(false);
  const [fileName, setFileName] = useState('');
  const applyFormat = (command: 'bold' | 'italic') => {
    document.execCommand(command);
    if (command === 'bold') setBold(!bold);
    else setItalic(!italic);
  };
  const attachFile = () => document.getElementById('compose-file')?.click();

  return (
    <>
      <PageHeading eyebrow="COMPOSE" title="New message" description="Write from the right account, with your team close by." actions={<Button onClick={() => setToast('Draft saved locally for this preview session.')} testId="button-save-draft">Save draft</Button>} />
      <div className="compose-wrap">
        <section className="panel compose-panel">
          <div className="compose-account-row"><label htmlFor="compose-account">From</label><select id="compose-account" value={from} onChange={(event) => setFrom(event.target.value)} aria-label="Sending account" data-testid="select-compose-account">{accounts.map((account) => <option key={account.address}>{account.address}</option>)}</select><Link href="/accounts" className="text-link" data-testid="link-manage-compose-accounts">Manage accounts</Link></div>
          <div className="compose-line"><label htmlFor="compose-to">To</label><input id="compose-to" placeholder="Add recipients" data-testid="input-compose-to" /><span><button type="button" onClick={() => setCc(!cc)} aria-expanded={cc} data-testid="button-toggle-cc">Cc</button><button type="button" onClick={() => setBcc(!bcc)} aria-expanded={bcc} data-testid="button-toggle-bcc">Bcc</button></span></div>
          {cc && <div className="compose-line"><label htmlFor="compose-cc">Cc</label><input id="compose-cc" placeholder="Add Cc recipients" data-testid="input-compose-cc" /></div>}
          {bcc && <div className="compose-line"><label htmlFor="compose-bcc">Bcc</label><input id="compose-bcc" placeholder="Add Bcc recipients" data-testid="input-compose-bcc" /></div>}
          <div className="compose-line"><label htmlFor="compose-subject">Subject</label><input id="compose-subject" placeholder="Add a subject" data-testid="input-compose-subject" /></div>
          <div className="editor-tools">
            <button type="button" className={bold ? 'active' : ''} aria-label="Bold" aria-pressed={bold} onMouseDown={(event) => event.preventDefault()} onClick={() => applyFormat('bold')} data-testid="button-format-bold"><Bold size={15} /></button>
            <button type="button" className={italic ? 'active' : ''} aria-label="Italic" aria-pressed={italic} onMouseDown={(event) => event.preventDefault()} onClick={() => applyFormat('italic')} data-testid="button-format-italic"><Italic size={15} /></button>
            <span />
            <button type="button" aria-label="Attach file" onClick={attachFile} data-testid="button-attach-file"><Paperclip size={15} /></button>
            <input id="compose-file" type="file" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) { setFileName(file.name); setToast('Attachment selected locally. It will not be uploaded in this preview.'); } }} data-testid="input-compose-file" />
            <button type="button" aria-label="Insert link" aria-expanded={linkEditor} onClick={() => setLinkEditor(!linkEditor)} data-testid="button-compose-link"><Link2 size={15} /></button>
            <button type="button" aria-label="Schedule send" aria-expanded={schedule} onClick={() => setSchedule(!schedule)} data-testid="button-schedule-send"><CalendarClock size={15} /></button>
            <button type="button" className="ai-editor-button" onClick={() => setToast('AI suggestions are not connected in this prototype.')} data-testid="button-compose-ai"><Sparkles size={14} /> Draft with AI</button>
          </div>
          {linkEditor && <div className="compose-link-panel"><label htmlFor="compose-link-url">Link address</label><input id="compose-link-url" type="url" value={linkUrl} onChange={(event) => setLinkUrl(event.target.value)} placeholder="https://example.com" data-testid="input-compose-link-url" /><button type="button" onClick={() => { if (linkUrl) document.execCommand('createLink', false, linkUrl); else setToast('Enter a link address to insert it in the draft.'); }} data-testid="button-insert-link">Insert link</button></div>}
          <div className="compose-editor" contentEditable suppressContentEditableWarning data-placeholder="Write your message…" data-testid="editor-compose" role="textbox" aria-label="Message body" />
          {fileName && <div className="compose-file-chip"><Paperclip size={13} />{fileName}<button type="button" aria-label="Remove selected attachment" onClick={() => { setFileName(''); const input = document.getElementById('compose-file') as HTMLInputElement | null; if (input) input.value = ''; }} data-testid="button-remove-attachment"><X size={12} /></button></div>}
          {schedule && <div className="schedule-strip"><CalendarDays size={16} /><span>Schedule for</span><input type="date" aria-label="Schedule date" data-testid="input-schedule-date" /><input type="time" aria-label="Schedule time" defaultValue="09:00" data-testid="input-schedule-time" /><button type="button" onClick={() => setToast('Scheduling requires a connected sending service.')} data-testid="button-set-schedule">Set schedule</button></div>}
          <div className="compose-footer"><div><Button kind="primary" icon={Send} onClick={() => setToast('Sending is disabled. Connect a sending service to send real email.')} testId="button-send-compose">Send <ChevronDown size={13} /></Button><button type="button" className="icon-button" aria-label="Attach a file" onClick={attachFile} data-testid="button-footer-attach"><Paperclip size={16} /></button><button type="button" className="icon-button" aria-label="Insert link" onClick={() => setLinkEditor(!linkEditor)} data-testid="button-footer-link"><Link2 size={16} /></button></div><span>From {from}</span></div>
        </section>
        <aside className="compose-aside">
          <div className="panel ai-aside"><span className="ai-kicker"><Sparkles size={13} /> WRITING ASSISTANT</span><h3>A second set of eyes</h3><p>Drafting tools can help with tone and clarity. You stay in control of every word.</p><Button onClick={() => setToast('AI suggestions are not connected in this prototype.')} testId="button-suggest-reply">Suggest a reply</Button><div className="ai-disclaimer">No message content is processed in this UI preview.</div></div>
          <div className="panel compose-tip"><h3>Before you send</h3><ul><li><CheckCircle2 size={14} /> Double-check recipients</li><li><CheckCircle2 size={14} /> Pick the right shared account</li><li><CheckCircle2 size={14} /> Keep teammates in the loop</li></ul></div>
        </aside>
      </div>
      <Toast message={toast} close={() => setToast('')} />
    </>
  );
}
