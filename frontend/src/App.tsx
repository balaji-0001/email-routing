import { lazy, Suspense, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MotionConfig } from 'framer-motion';
import { Redirect, Router, useLocation, useSearch } from 'wouter';
import { ErrorBoundary } from '@/components/error-boundary';
import { SkeletonRows, ToastProvider } from '@/components/kit';
import { Shell } from '@/components/shell';
import { pageTitles } from '@/data';
import { setSignedOutHandler } from '@/lib/api';
import { SessionProvider, isSignedIn, useMe } from '@/lib/session';
import { ForgotPasswordPage, InviteAcceptPage, LoginPage, RegisterPage, ResetPasswordPage, Splash, WorkspaceSetupPage } from '@/pages/auth';
import { Dashboard } from '@/pages/dashboard';
import { AccountsPage, AddAccountPage } from '@/pages/accounts';
import { AI_PATHS, AiPage } from '@/pages/ai';
import { AutomationPage } from '@/pages/automation';
import { ScheduledPage } from '@/pages/reminders';
import { ContactsPage, NotesPage, NotificationsPage, TemplatesPage } from '@/pages/collab';
import { LabelsPage, MAIL_PATHS, MailPage } from '@/pages/mail';
import { NotFoundPage, PLACEHOLDERS, PlaceholderPage } from '@/pages/placeholders';
import { SettingsPage } from '@/pages/settings';
import { InvitePage, RolesPage, TeamPage } from '@/pages/team';

// The chart library is large and only this page uses it, so it is fetched when the page is opened.
const AnalyticsPage = lazy(() => import('@/pages/analytics').then((module) => ({ default: module.AnalyticsPage })));

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } });

// When any request finds the session gone, drop to the sign-in screen.
setSignedOutHandler(() => queryClient.setQueryData(['me'], null));

const SIGN_IN_SCREENS: Partial<Record<string, () => ReactNode>> = {
  '/login': LoginPage,
  '/register': RegisterPage,
  '/forgot-password': ForgotPasswordPage,
};

/** Where to go after signing in, if the address asked for somewhere inside the app. */
function nextPath(search: string): string | null {
  const next = new URLSearchParams(search).get('next');
  return next && next.startsWith('/') && !next.startsWith('//') ? next : null;
}

function Screen({ path }: { path: string }) {
  if (path === '/dashboard') return <Dashboard />;
  if (path === '/analytics') return <Suspense fallback={<section className="panel"><SkeletonRows rows={5} /></section>}><AnalyticsPage /></Suspense>;
  if (MAIL_PATHS.includes(path)) return <MailPage path={path} />;
  // Older links to one conversation open it in the reading pane.
  if (path.startsWith('/email/')) return <Redirect to={`/inbox?c=${Number(path.replace('/email/', '')) || ''}`} replace />;
  if (path === '/labels') return <LabelsPage />;
  if (path === '/contacts') return <ContactsPage />;
  if (path === '/templates') return <TemplatesPage />;
  if (path === '/notifications') return <NotificationsPage />;
  if (path === '/internal-notes') return <NotesPage />;
  if (path === '/automation' || path === '/automation/assignment' || path === '/automation/labels-priority') return <AutomationPage path={path} />;
  if (AI_PATHS.includes(path)) return <AiPage path={path} />;
  if (path === '/automation/scheduled-actions') return <ScheduledPage path={path} />;
  if (path === '/accounts') return <AccountsPage />;
  if (path === '/accounts/add') return <AddAccountPage />;
  if (path === '/accounts/connect/gmail') return <AddAccountPage provider="gmail" />;
  if (path === '/accounts/connect/outlook') return <AddAccountPage provider="microsoft" />;
  if (path === '/accounts/connect/imap') return <AddAccountPage provider="imap" />;
  if (path === '/settings/accounts') return <AccountsPage />;
  if (path === '/team') return <TeamPage />;
  if (path === '/team/invite') return <InvitePage />;
  if (path === '/team/roles') return <RolesPage />;
  if (path.startsWith('/settings') && pageTitles[path]) return <SettingsPage path={path} />;
  if (PLACEHOLDERS[path]) return <PlaceholderPage path={path} />;
  return <NotFoundPage />;
}

/** Decides what a visitor may see: sign-in screens, workspace setup, or the app. */
function Gate() {
  const [path] = useLocation();
  const search = useSearch();
  const me = useMe();

  if (me.isPending) return <Splash />;
  if (me.isError) return <Splash problem="Check that the API is running, then try again." retry={() => me.refetch()} />;

  // A reset link works whether or not this browser is signed in.
  if (path === '/reset-password') return <ResetPasswordPage />;

  // An invitation link works whether or not this browser is signed in.
  if (path.startsWith('/invite/')) {
    const token = path.replace('/invite/', '');
    return <InviteAcceptPage token={token} me={me.data} />;
  }

  const SignInScreen = SIGN_IN_SCREENS[path];
  if (!me.data) {
    if (SignInScreen) return <SignInScreen />;
    const wanted = path === '/' || path === '/workspace/setup' ? '' : `?next=${encodeURIComponent(path + (search ? `?${search}` : ''))}`;
    return <Redirect to={`/login${wanted}`} replace />;
  }

  if (!isSignedIn(me.data)) {
    return path === '/workspace/setup' ? <WorkspaceSetupPage me={me.data} /> : <Redirect to="/workspace/setup" replace />;
  }

  if (SignInScreen || path === '/workspace/setup' || path === '/') return <Redirect to={nextPath(search) ?? '/dashboard'} replace />;

  return (
    <SessionProvider value={me.data}>
      <Shell><Screen path={path} /></Shell>
    </SessionProvider>
  );
}

function RouteBoundary({ children }: { children: ReactNode }) {
  const [path] = useLocation();
  return <ErrorBoundary resetKey={path}>{children}</ErrorBoundary>;
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <Router base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
            <RouteBoundary><Gate /></RouteBoundary>
          </Router>
        </ToastProvider>
      </QueryClientProvider>
    </MotionConfig>
  );
}
