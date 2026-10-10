import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { Link, useLocation } from 'wouter';
import {
  AlignLeft, Archive, Bell, Bot, Building2, CalendarClock, ChartNoAxesCombined, Check, ChevronDown, ChevronRight, CircleHelp,
  CircleUserRound, ContactRound, Ellipsis, FileEdit, FileText, Folder, Gauge, Inbox, LayoutDashboard, ListTodo, LockKeyhole,
  LogOut, Mail, Menu, MessageSquareText, Plus, Route, ScanSearch, ScrollText, Search, Send, Settings, ShieldCheck, Sparkles,
  Star, StickyNote, Tags, Trash, UserPlus, UserRoundCog, Users, Webhook, Workflow, type LucideIcon,
} from 'lucide-react';
import { Aurora } from '@/components/aurora';
import { BrandMark } from '@/components/brand';
import { Avatar, useToast } from '@/components/kit';
import { navGroups, pageTitles } from '@/data';
import { api } from '@/lib/api';
import { initials, titleCase } from '@/lib/format';
import { useAuthActions, useSession } from '@/lib/session';
import { ThemePicker } from '@/lib/theme';

const NAV_ICONS: Record<string, LucideIcon> = {
  AlignLeft, Archive, Bell, Bot, Building2, CalendarClock, ChartNoAxesCombined, CircleUserRound, ContactRound, FileEdit, FileText,
  Folder, Gauge, Inbox, LayoutDashboard, ListTodo, LockKeyhole, Mail, MessageSquareText, Plus, Route, ScanSearch, ScrollText,
  Search, Send, Settings, ShieldCheck, Sparkles, Star, StickyNote, Tags, Trash, UserPlus, UserRoundCog, Users, Webhook, Workflow,
};

type Menu = 'workspace' | 'profile' | 'help' | 'account' | null;

function Popover({ className, label, up = false, children }: { className: string; label: string; up?: boolean; children: ReactNode }) {
  const from = up ? 6 : -6;
  return (
    <motion.div
      className={`shell-popover ${className}`}
      role="menu"
      aria-label={label}
      initial={{ opacity: 0, y: from, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: from * 0.6, scale: 0.98 }}
      transition={{ duration: 0.14, ease: [0.2, 0.8, 0.2, 1] }}
    >
      {children}
    </motion.div>
  );
}

/** Sidebar, top bar and the page area every signed-in screen sits in. */
export function Shell({ children }: { children: ReactNode }) {
  const [path, navigate] = useLocation();
  const { user, workspace, role } = useSession();
  const { logout } = useAuthActions();
  const toast = useToast();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menu, setMenu] = useState<Menu>(null);
  const [search, setSearch] = useState('');
  const pageRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setMobileOpen(false); setMenu(null); }, [path]);

  useEffect(() => {
    if (!menu) return;
    const onDown = (event: MouseEvent) => { if (!(event.target as HTMLElement).closest('[data-popover-root]')) setMenu(null); };
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenu(null); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [menu]);

  // Animate in place rather than remounting, so page state survives navigation.
  useLayoutEffect(() => {
    const element = pageRef.current;
    if (!element || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    element.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 300, easing: 'cubic-bezier(.2,.8,.2,1)' });
  }, [path]);

  const client = useQueryClient();
  const myWorkspaces = useQuery({ queryKey: ['my-workspaces'], queryFn: api.myWorkspaces });
  const switchWs = useMutation({
    mutationFn: api.switchWorkspace,
    onSuccess: (me) => {
      client.setQueryData(['me'], me);
      client.invalidateQueries();
      toast(`Switched to ${me.workspace?.name}`);
      setMenu(null);
    },
  });

  const notifications = useQuery({ queryKey: ['notifications'], queryFn: api.notifications, refetchInterval: 20000 });
  const unread = notifications.data?.unread ?? 0;

  const toggle = (which: Exclude<Menu, null>) => setMenu(menu === which ? null : which);

  async function signOut() {
    setMenu(null);
    try {
      await logout.mutateAsync();
    } catch {
      // The session is cleared on this device either way.
    }
    navigate('/login', { replace: true });
    toast('You are signed out.');
  }

  const title = pageTitles[path] ?? (path.startsWith('/email/') ? 'Conversation' : 'Page not found');

  return (
    <div className="app-shell">
      <Aurora soft />
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
        <Link href="/dashboard" className="brand" data-testid="link-home">
          <BrandMark size={46} />
          <span>Email Routing</span>
        </Link>

        <div className="popover-root workspace-root" data-popover-root>
          <button type="button" className="workspace-switch" aria-haspopup="menu" aria-expanded={menu === 'workspace'} onClick={() => toggle('workspace')} data-testid="button-workspace-switch">
            <span className="workspace-avatar">{initials(workspace.name).charAt(0)}</span>
            <span className="workspace-copy"><b data-testid="text-workspace-name">{workspace.name}</b><small>Team workspace</small></span>
            <ChevronDown size={17} className="chevron" />
          </button>
          <AnimatePresence>
            {menu === 'workspace' && (
              <Popover className="workspace-popover" label="Workspace">
                <b>{workspace.name}</b>
                <span>You are {role === 'owner' || role === 'admin' || role === 'agent' ? 'an' : 'a'} {role} here</span>
                <Link href="/settings/workspace">Workspace settings</Link>
                <Link href="/team">Team members</Link>
                {myWorkspaces.data && myWorkspaces.data.length > 1 && (
                  <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                    <small style={{ display: 'block', marginBottom: '0.25rem', opacity: 0.7, fontWeight: 600 }}>Switch workspace</small>
                    {myWorkspaces.data.map((ws) => (
                      <button
                        key={ws.id}
                        type="button"
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          width: '100%',
                          textAlign: 'left',
                          padding: '0.35rem 0.5rem',
                          background: ws.is_current ? 'rgba(255,255,255,0.15)' : 'transparent',
                          border: 'none',
                          borderRadius: '6px',
                          color: 'inherit',
                          cursor: ws.is_current ? 'default' : 'pointer',
                          fontSize: '0.875rem',
                        }}
                        onClick={() => {
                          if (!ws.is_current) switchWs.mutate(ws.id);
                        }}
                        disabled={ws.is_current || switchWs.isPending}
                      >
                        <span>{ws.name} <small style={{ opacity: 0.7 }}>({ws.role})</small></span>
                        {ws.is_current && <Check size={14} />}
                      </button>
                    ))}
                  </div>
                )}
              </Popover>
            )}
          </AnimatePresence>
        </div>

        <Link href="/compose" className="compose-button" data-testid="link-compose"><Plus size={18} /> Compose <kbd>C</kbd></Link>

        <nav className="side-nav" aria-label="Main navigation">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.title}>
              <div className="nav-label">{group.title}</div>
              {/* Preferences is one entry; its sections are tabs inside the Settings page. */}
              {(group.title === 'PREFERENCES' ? group.items.slice(0, 1) : group.items).map(([href, label, icon]) => {
                const Icon = NAV_ICONS[icon] ?? Mail;
                const active = href === '/settings' ? path.startsWith('/settings') : path === href;
                return (
                  <Link href={href} className={`nav-item ${active ? 'active' : ''}`} key={href} data-testid={`link-nav-${href.replaceAll('/', '-').slice(1)}`}>
                    <Icon size={18} />
                    <span>{label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="popover-root" data-popover-root>
            <AnimatePresence>
              {menu === 'profile' && (
                <Popover className="profile-popover" label="Account" up>
                  <Link href="/settings/profile"><CircleUserRound size={17} /> Your profile</Link>
                  <Link href="/settings/security"><LockKeyhole size={17} /> Security</Link>
                  <button type="button" onClick={signOut} disabled={logout.isPending} data-testid="button-sign-out"><LogOut size={17} /> Sign out</button>
                </Popover>
              )}
            </AnimatePresence>
            <button type="button" className="profile-menu" aria-haspopup="menu" aria-expanded={menu === 'profile'} onClick={() => toggle('profile')} data-testid="button-profile-menu">
              <Avatar name={user.name} />
              <span><b data-testid="text-user-name">{user.name}</b><small>{titleCase(role)}</small></span>
              <Ellipsis size={20} />
            </button>
          </div>
        </div>
      </aside>

      {mobileOpen && <button type="button" className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}

      <main className="main-area">
        <header className="topbar">
          <button type="button" className="mobile-menu icon-button" aria-label="Open menu" aria-expanded={mobileOpen} onClick={() => setMobileOpen(!mobileOpen)}><Menu size={22} /></button>
          <div className="crumb"><span>{workspace.name}</span><ChevronRight size={16} /><b>{title}</b></div>
          <div className="top-actions">
            <label className="global-search">
              <Search size={18} />
              <input
                placeholder="Search all mail..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') navigate(`/search?q=${encodeURIComponent(search.trim())}`); }}
                aria-label="Search all mail"
                data-testid="input-global-search"
              />
            </label>
            <div className="popover-root" data-popover-root>
              <button type="button" className="icon-button" aria-label="Help" aria-haspopup="dialog" aria-expanded={menu === 'help'} onClick={() => toggle('help')} data-testid="button-help"><CircleHelp size={21} /></button>
              <AnimatePresence>
                {menu === 'help' && (
                  <Popover className="help-popover" label="Help">
                    <b>Help</b>
                    <span>A help center is not available yet.</span>
                  </Popover>
                )}
              </AnimatePresence>
            </div>
            <Link href="/notifications" className="icon-button bell-button" aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'} data-testid="link-notifications">
              <Bell size={21} />{unread > 0 && <i className="bell-count" data-testid="text-unread-notifications">{unread > 9 ? '9+' : unread}</i>}
            </Link>
            <div className="popover-root" data-popover-root>
              <button type="button" className="top-avatar-link" aria-label="Your account" aria-haspopup="menu" aria-expanded={menu === 'account'} onClick={() => toggle('account')} data-testid="button-top-account">
                <Avatar name={user.name} className="top-avatar" />
              </button>
              <AnimatePresence>
                {menu === 'account' && (
                  <Popover className="account-popover" label="Your account">
                    <b data-testid="text-account-name">{user.name}</b>
                    <span>{user.email} · {titleCase(role)}</span>
                    <Link href="/settings/profile"><CircleUserRound size={17} /> Your profile</Link>
                    <Link href="/accounts"><Mail size={17} /> Connected email accounts</Link>
                    <Link href="/team"><Users size={17} /> Team members</Link>
                    <Link href="/settings/security"><LockKeyhole size={17} /> Security</Link>
                    <Link href="/settings"><Settings size={17} /> Settings</Link>
                    <div className="popover-section"><small>Appearance</small><ThemePicker /></div>
                    <button type="button" onClick={signOut} disabled={logout.isPending} data-testid="button-top-sign-out"><LogOut size={17} /> Sign out</button>
                  </Popover>
                )}
              </AnimatePresence>
            </div>
          </div>
        </header>
        <div className="page-content"><div ref={pageRef}>{children}</div></div>
      </main>
    </div>
  );
}
