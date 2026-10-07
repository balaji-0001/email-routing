import { useState } from 'react';
import { Bell, Building2, Check, ChevronDown, ChevronRight, CircleHelp, Mail, Menu, Search, Settings, UserRound, X } from 'lucide-react';
import { Link, useLocation } from 'wouter';
import { navGroups, pageTitles } from '../data';
import { Toast } from './prototype-ui';
import {
  Activity, AlignLeft, Archive, Bot, CalendarClock, CircleUserRound, ContactRound,
  FileEdit, FileText, Gauge, Inbox, LayoutDashboard, ListTodo, LockKeyhole,
  MailOpen, MessageSquareText, Plus, Route, ScanSearch, ScrollText, Send, ShieldCheck,
  Sparkles, Star, StickyNote, Tags, Trash, UserPlus, UserRoundCog, Workflow,
} from 'lucide-react';

const navIcons: Record<string, any> = {
  LayoutDashboard, Inbox, FileEdit, Send, Star, Archive, Trash, Search, Tags,
  Folder: Building2, ContactRound, FileText, Bell, Users: UserRound, UserPlus,
  ShieldCheck, ListTodo, StickyNote, Mail, Plus, Sparkles, AlignLeft,
  MessageSquareText, ScanSearch, Gauge, Route, Bot, Workflow, UserRoundCog,
  CalendarClock, Settings, Building2, CircleUserRound, LockKeyhole,
  ChartNoAxesCombined: Activity, ScrollText,
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const [path, navigate] = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menu, setMenu] = useState<'workspace' | 'profile' | 'help' | null>(null);
  const [search, setSearch] = useState('');
  const [toast, setToast] = useState('');

  const runSearch = () => {
    sessionStorage.setItem('northstar-search-query', search);
    navigate('/search');
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
        <Link href="/dashboard" className="brand" data-testid="link-home">
          <div className="brand-mark"><span /><span /><span /></div>
          <span>northstar</span>
          <span className="prototype-pill">UI preview</span>
        </Link>

        <button
          type="button"
          className="workspace-switch"
          onClick={() => setMenu(menu === 'workspace' ? null : 'workspace')}
          aria-expanded={menu === 'workspace'}
          data-testid="button-workspace-switch"
        >
          <span className="workspace-avatar">N</span>
          <span className="workspace-copy"><b>Northstar Studio</b><small>Team workspace</small></span>
          <ChevronDown size={15} />
        </button>
        {menu === 'workspace' && (
          <div className="shell-popover workspace-popover" role="menu">
            <b>Northstar Studio</b>
            <span>Shared team workspace</span>
            <Link href="/settings/workspace" onClick={() => setMenu(null)}>Workspace settings</Link>
            <button type="button" onClick={() => { setMenu(null); setToast('Workspace switching is not available in this preview.'); }}>Switch workspace</button>
          </div>
        )}

        <Link href="/compose" className="compose-button" onClick={() => setMobileOpen(false)} data-testid="link-compose">
          <Plus size={16} /> Compose <kbd>C</kbd>
        </Link>
        <nav className="side-nav" aria-label="Main navigation">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.title}>
              <div className="nav-label">{group.title}</div>
              {group.items.map(([href, label, icon]) => {
                const Icon = navIcons[icon] || Mail;
                const active = path === href || (href === '/inbox' && path === '/');
                return (
                  <Link
                    href={href}
                    className={`nav-item ${active ? 'active' : ''}`}
                    key={href}
                    onClick={() => setMobileOpen(false)}
                    data-testid={`link-nav-${href.replaceAll('/', '-').slice(1)}`}
                  >
                    <Icon size={16} />
                    <span>{label}</span>
                    {href === '/inbox' && <b className="nav-count">12</b>}
                    {href === '/notifications' && <i className="nav-dot" />}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="sync-status">
            <span className="sync-dot" />
            <div><b>All inboxes synced</b><small>Last checked just now</small></div>
            <Check size={14} />
          </div>
          <button
            type="button"
            className="profile-menu"
            onClick={() => setMenu(menu === 'profile' ? null : 'profile')}
            aria-expanded={menu === 'profile'}
            data-testid="button-profile-menu"
          >
            <span className="avatar avatar-blue">AM</span>
            <span><b>Alex Morgan</b><small>Workspace admin</small></span>
            <ChevronDown size={16} />
          </button>
          {menu === 'profile' && (
            <div className="shell-popover profile-popover" role="menu">
              <Link href="/settings/profile" onClick={() => setMenu(null)}><UserRound size={14} /> Your profile</Link>
              <Link href="/settings/security" onClick={() => setMenu(null)}><ShieldCheck size={14} /> Security</Link>
              <button type="button" onClick={() => { setMenu(null); setToast('Sign out is not connected in this UI preview.'); }}>Sign out</button>
            </div>
          )}
        </div>
      </aside>

      {mobileOpen && (
        <button
          type="button"
          className="mobile-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
          data-testid="button-close-mobile-navigation"
        />
      )}
      <main className="main-area">
        <header className="topbar">
          <button
            type="button"
            className="mobile-menu icon-button"
            aria-label="Open navigation"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen(!mobileOpen)}
            data-testid="button-open-mobile-navigation"
          >
            <Menu size={19} />
          </button>
          <div className="crumb">
            <span>Northstar Studio</span><ChevronRight size={14} />
            <b>{pageTitles[path] || (path.startsWith('/email/') ? 'Conversation' : 'Overview')}</b>
          </div>
          <div className="top-actions">
            <label className="global-search">
              <Search size={16} />
              <input
                placeholder="Search all mail..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') runSearch(); }}
                data-testid="input-global-search"
              />
              <kbd>⌘ K</kbd>
            </label>
            <button
              type="button"
              className="icon-button"
              aria-label="Help"
              onClick={() => setMenu(menu === 'help' ? null : 'help')}
              aria-expanded={menu === 'help'}
              data-testid="button-help"
            >
              <CircleHelp size={18} />
            </button>
            {menu === 'help' && (
              <div className="shell-popover help-popover" role="dialog" aria-label="Help">
                <b>Northstar help</b>
                <span>Help center is not connected in this UI preview.</span>
                <button type="button" onClick={() => { setMenu(null); setToast('Help center is not available in this preview.'); }}>Contact support</button>
                <button type="button" aria-label="Close help" onClick={() => setMenu(null)}><X size={13} /> Close</button>
              </div>
            )}
            <Link href="/notifications" className="icon-button notification-trigger" aria-label="Notifications" data-testid="link-notifications">
              <Bell size={18} /><i />
            </Link>
            <Link href="/settings/profile" className="avatar avatar-blue top-avatar" aria-label="Open profile" data-testid="link-top-profile">AM</Link>
          </div>
        </header>
        <div className="page-content">{children}</div>
        <div className="prototype-footer"><span className="prototype-dot" /> Prototype mode <span>•</span> UI only — no mail is sent or synced</div>
      </main>
      <Toast message={toast} close={() => setToast('')} />
    </div>
  );
}
