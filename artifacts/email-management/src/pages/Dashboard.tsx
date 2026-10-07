import { useState } from 'react';
import { Link, useLocation } from 'wouter';
import { ArrowRight, Clock3, Inbox, Mail, MoreHorizontal, Plus, CheckCheck } from 'lucide-react';
import { accounts, mails } from '../data';
import { ActivityItem, Button, Metric, PageHeading, Toast } from '../components/prototype-ui';
import { MailRow } from './MailScreens';

export default function Dashboard() {
  const [, navigate] = useLocation();
  const [toast, setToast] = useState('');
  const [activityMenu, setActivityMenu] = useState(false);

  return (
    <>
      <PageHeading
        eyebrow="MONDAY, JUNE 17"
        title="Good morning, Alex"
        description="Here’s what’s happening across your shared inboxes."
        actions={<Button kind="primary" icon={Plus} onClick={() => navigate('/compose')} testId="button-new-message">New message</Button>}
      />
      <div className="welcome-strip">
        <div className="welcome-icon"><Inbox size={20} /></div>
        <div><b>Your team’s command center</b><p>Three accounts are connected. Your conversations are together, but still yours to control.</p></div>
        <Link href="/accounts" className="text-link" data-testid="link-manage-accounts">Manage accounts <ArrowRight size={14} /></Link>
      </div>
      <div className="metric-grid">
        <Metric title="Open conversations" value="38" delta="7 need a reply" icon={Inbox} accent="blue" />
        <Metric title="Waiting on your team" value="12" delta="Across 2 shared inboxes" icon={Clock3} accent="amber" />
        <Metric title="Resolved today" value="24" delta="Team average · 18" icon={CheckCheck} accent="green" />
        <Metric title="Connected inboxes" value="3" delta="All accounts healthy" icon={Mail} accent="violet" />
      </div>
      <div className="dashboard-grid">
        <section className="panel overview-panel">
          <div className="panel-head">
            <div><h2>Needs your attention</h2><p>Priority conversations, across every account</p></div>
            <Link href="/inbox" className="text-link" data-testid="link-dashboard-inbox">View inbox <ArrowRight size={14} /></Link>
          </div>
          <div className="attention-list">
            {mails.slice(0, 4).map((mail) => <MailRow key={mail.id} mail={mail} compact />)}
          </div>
        </section>
        <section className="panel activity-panel">
          <div className="panel-head">
            <div><h2>Team activity</h2><p>A little movement goes a long way</p></div>
            <div className="popover-anchor">
              <button type="button" className="icon-button" aria-label="More activity options" aria-expanded={activityMenu} onClick={() => setActivityMenu(!activityMenu)} data-testid="button-activity-options">
                <MoreHorizontal size={17} />
              </button>
              {activityMenu && (
                <div className="shell-popover" role="menu">
                  <button type="button" onClick={() => { setActivityMenu(false); setToast('Activity marked as seen in this local preview.'); }}>Mark activity as seen</button>
                  <button type="button" onClick={() => { setActivityMenu(false); setToast('Activity filters are available in the Notifications view.'); }}>Activity preferences</button>
                </div>
              )}
            </div>
          </div>
          <div className="activity-feed">
            <ActivityItem initials="PS" tone="peach" text={<><b>Priya Shah</b> assigned a conversation to you</>} sub="Access issue after workspace migration" time="4 min ago" />
            <ActivityItem initials="JL" tone="mint" text={<><b>Jordan Lee</b> added a private note</>} sub="Website feedback — mobile navigation" time="18 min ago" />
            <ActivityItem initials="AM" tone="blue" text={<><b>You</b> resolved a conversation</>} sub="New vendor onboarding" time="32 min ago" />
            <ActivityItem initials="SP" tone="lavender" text={<><b>Samir Patel</b> moved a conversation to Finance</>} sub="June expense report" time="1 hr ago" />
          </div>
          <Link href="/team" className="activity-link" data-testid="link-team-activity">See team workspace <ArrowRight size={14} /></Link>
        </section>
      </div>
      <section className="panel accounts-overview">
        <div className="panel-head">
          <div><h2>Connected inboxes</h2><p>One queue, three points of view</p></div>
          <Link href="/accounts" className="text-link" data-testid="link-dashboard-accounts">Manage <ArrowRight size={14} /></Link>
        </div>
        <div className="account-mini-list">
          {accounts.map((account) => (
            <div className="account-mini" key={account.address} data-testid={`account-status-${account.provider.toLowerCase().replaceAll(' ', '-')}`}>
              <span className="provider-mark" style={{ '--provider': account.color } as React.CSSProperties}>{account.provider === 'Gmail' ? 'G' : account.provider === 'IMAP / SMTP' ? 'I' : 'M'}</span>
              <div className="account-mini-copy"><b>{account.address}</b><small>{account.provider}</small></div>
              <span className="status-pill"><i />{account.status}</span>
              <span className="account-count">{account.count} messages</span>
              <span className="account-sync">{account.sync}</span>
            </div>
          ))}
        </div>
      </section>
      <Toast message={toast} close={() => setToast('')} />
    </>
  );
}
