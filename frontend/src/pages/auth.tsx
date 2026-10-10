import { useState, type FormEvent, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useSearch } from 'wouter';
import { ArrowRight, Building2, Check, CircleAlert, CircleUserRound, Eye, EyeOff, LockKeyhole, Mail, MailCheck, type LucideIcon } from 'lucide-react';
import { Aurora } from '@/components/aurora';
import { BrandMark } from '@/components/brand';
import { useToast } from '@/components/kit';
import { ApiError, api, type Me } from '@/lib/api';
import { localTimezone } from '@/lib/format';
import { useAuthActions } from '@/lib/session';

/** The frosted card on the flowing backdrop that every sign-in screen shares. */
function AuthFrame({ title, subtitle, children, below }: { title: string; subtitle: string; children: ReactNode; below?: ReactNode }) {
  return (
    <div className="auth-screen">
      <Aurora />
      <div className="auth-shapes" aria-hidden="true"><i /><i /><i /><i /><i /><i /></div>
      <Link href="/login" className="brand auth-brand"><BrandMark size={48} /><span>Email Routing</span></Link>
      <main className="auth-main">
        <div className="auth-card">
          <h1>{title}</h1>
          <p className="auth-sub">{subtitle}</p>
          {children}
        </div>
        {below}
      </main>
    </div>
  );
}

function AuthField({ label, value, onChange, type = 'text', placeholder, icon: Icon, error, autoComplete, minLength, autoFocus = false }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  icon: LucideIcon;
  error?: string;
  autoComplete?: string;
  minLength?: number;
  autoFocus?: boolean;
}) {
  const [shown, setShown] = useState(false);
  const password = type === 'password';
  const id = `auth-${label.toLowerCase().replaceAll(' ', '-')}`;
  return (
    <div className="auth-field-wrap">
      <label className={`auth-field ${error ? 'auth-field-invalid' : ''}`}>
        <span>{label}</span>
        <input
          type={password && shown ? 'text' : type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          minLength={minLength}
          autoFocus={autoFocus}
          required
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
          data-testid={`input-${label.toLowerCase().replaceAll(' ', '-')}`}
        />
        {password ? (
          <button type="button" className="auth-field-icon" onClick={() => setShown(!shown)} aria-label={shown ? 'Hide password' : 'Show password'} aria-pressed={shown}>
            {shown ? <EyeOff size={21} /> : <Eye size={21} />}
          </button>
        ) : (
          <span className="auth-field-icon"><Icon size={21} /></span>
        )}
      </label>
      {error && <p className="auth-field-error" id={`${id}-error`} role="alert">{error}</p>}
    </div>
  );
}

function Notice({ tone = 'error', children }: { tone?: 'error' | 'info' | 'success'; children: ReactNode }) {
  const Icon = tone === 'success' ? MailCheck : CircleAlert;
  return <div className={`auth-notice auth-notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'} data-testid={`notice-${tone}`}><Icon size={20} /><span>{children}</span></div>;
}

function Submit({ busy, children }: { busy: boolean; children: ReactNode }) {
  return <button type="submit" className="auth-submit" disabled={busy} data-testid="button-submit">{children}<ArrowRight size={23} /></button>;
}

/** A failed request, split into the message for the whole form and the ones for single fields. */
function useFormError(error: unknown) {
  const failure = error instanceof ApiError ? error : null;
  return {
    general: failure && !failure.details.length ? failure.message : error && !failure ? 'Something went wrong. Please try again.' : null,
    field: (name: string) => failure?.field(name),
  };
}

function AuthSwitch({ question, href, action }: { question: string; href: string; action: string }) {
  return <div className="auth-switch">{question} <Link href={href}>{action}</Link></div>;
}

export function LoginPage() {
  const { login } = useAuthActions();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const error = useFormError(login.error);

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate({ email, password, remember });
  }

  return (
    <AuthFrame title="Welcome back." subtitle="Pick up where your team left off." below={<AuthSwitch question="New to Email Routing?" href="/register" action="Create an account" />}>
      <form onSubmit={submit}>
        {error.general && <Notice>{error.general}</Notice>}
        <AuthField label="Work email" value={email} onChange={setEmail} type="email" placeholder="you@company.com" icon={Mail} error={error.field('email')} autoComplete="email" autoFocus />
        <AuthField label="Password" value={password} onChange={setPassword} type="password" placeholder="Your password" icon={LockKeyhole} error={error.field('password')} autoComplete="current-password" />
        <div className="auth-row">
          <Link href="/forgot-password" className="auth-forgot">Forgot password?</Link>
          <label className="auth-remember">
            <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} data-testid="checkbox-remember" />
            <i><Check size={16} /></i>Remember me
          </label>
        </div>
        <Submit busy={login.isPending}>{login.isPending ? 'Signing in…' : 'Sign in'}</Submit>
      </form>
    </AuthFrame>
  );
}

export function RegisterPage() {
  const { register } = useAuthActions();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const error = useFormError(register.error);

  function submit(event: FormEvent) {
    event.preventDefault();
    register.mutate({ name, email, password, timezone: localTimezone() });
  }

  return (
    <AuthFrame title="Make room for good work." subtitle="Bring your team’s inboxes into one considered workspace." below={<AuthSwitch question="Already have an account?" href="/login" action="Sign in" />}>
      <form onSubmit={submit}>
        {error.general && <Notice>{error.general}</Notice>}
        <AuthField label="Your name" value={name} onChange={setName} placeholder="First and last name" icon={CircleUserRound} error={error.field('name')} autoComplete="name" autoFocus />
        <AuthField label="Work email" value={email} onChange={setEmail} type="email" placeholder="you@company.com" icon={Mail} error={error.field('email')} autoComplete="email" />
        <AuthField label="Password" value={password} onChange={setPassword} type="password" placeholder="At least 8 characters" icon={LockKeyhole} error={error.field('password')} autoComplete="new-password" minLength={8} />
        <Submit busy={register.isPending}>{register.isPending ? 'Creating your account…' : 'Create account'}</Submit>
      </form>
    </AuthFrame>
  );
}

export function ForgotPasswordPage() {
  const options = useQuery({ queryKey: ['auth-options'], queryFn: api.options, staleTime: 60_000 });
  const forgot = useMutation({ mutationFn: api.forgotPassword });
  const [email, setEmail] = useState('');
  const error = useFormError(forgot.error);
  const unavailable = options.data?.password_reset_available === false || (forgot.error instanceof ApiError && forgot.error.code === 'EMAIL_NOT_CONFIGURED');

  function submit(event: FormEvent) {
    event.preventDefault();
    forgot.mutate(email);
  }

  return (
    <AuthFrame title="Let’s get you back in." subtitle="Enter your work email and we’ll send you a link to choose a new password." below={<AuthSwitch question="Remember your password?" href="/login" action="Sign in" />}>
      {unavailable ? (
        <Notice tone="info">Password reset by email is not set up on this server yet. Ask the person who runs it to reset your password.</Notice>
      ) : forgot.isSuccess ? (
        <Notice tone="success">If {email} has an account, a reset link is on its way. It works once and expires in an hour.</Notice>
      ) : (
        <form onSubmit={submit}>
          {error.general && <Notice>{error.general}</Notice>}
          <AuthField label="Work email" value={email} onChange={setEmail} type="email" placeholder="you@company.com" icon={Mail} error={error.field('email')} autoComplete="email" autoFocus />
          <Submit busy={forgot.isPending || options.isLoading}>{forgot.isPending ? 'Sending…' : 'Send reset link'}</Submit>
        </form>
      )}
    </AuthFrame>
  );
}

export function ResetPasswordPage() {
  const token = new URLSearchParams(useSearch()).get('token') ?? '';
  const [, navigate] = useLocation();
  const toast = useToast();
  const [password, setPassword] = useState('');
  const reset = useMutation({
    mutationFn: api.resetPassword,
    onSuccess: () => {
      toast('Password updated. Sign in with your new password.');
      navigate('/login', { replace: true });
    },
  });
  const error = useFormError(reset.error);

  function submit(event: FormEvent) {
    event.preventDefault();
    reset.mutate({ token, password });
  }

  return (
    <AuthFrame title="Choose a new password." subtitle="You’ll be signed out everywhere else and can sign in with the new one." below={<AuthSwitch question="Need a new link?" href="/forgot-password" action="Ask for another" />}>
      {!token ? (
        <Notice>This reset link is incomplete. Open the link from your email again, or ask for a new one.</Notice>
      ) : (
        <form onSubmit={submit}>
          {(error.general || error.field('token')) && <Notice>{error.general ?? 'This reset link is not valid any more. Ask for a new one.'}</Notice>}
          <AuthField label="New password" value={password} onChange={setPassword} type="password" placeholder="At least 8 characters" icon={LockKeyhole} error={error.field('password')} autoComplete="new-password" minLength={8} autoFocus />
          <Submit busy={reset.isPending}>{reset.isPending ? 'Saving…' : 'Save new password'}</Submit>
        </form>
      )}
    </AuthFrame>
  );
}

/** Shown to someone who has an account but no workspace yet. */
export function WorkspaceSetupPage({ me }: { me: Me }) {
  const { createWorkspace, logout } = useAuthActions();
  const [name, setName] = useState('');
  const error = useFormError(createWorkspace.error);

  function submit(event: FormEvent) {
    event.preventDefault();
    createWorkspace.mutate(name);
  }

  const below = (
    <div className="auth-switch">
      Signed in as {me.user.email}. <button type="button" onClick={() => logout.mutate()} data-testid="button-sign-out">Sign out</button>
    </div>
  );

  return (
    <AuthFrame title="Set up your workspace." subtitle={`One last step, ${me.user.first_name}. Name the shared home your team’s inboxes will live in.`} below={below}>
      <form onSubmit={submit}>
        {error.general && <Notice>{error.general}</Notice>}
        <AuthField label="Workspace name" value={name} onChange={setName} placeholder="Your company or team" icon={Building2} error={error.field('name')} autoComplete="organization" autoFocus />
        <Submit busy={createWorkspace.isPending}>{createWorkspace.isPending ? 'Creating…' : 'Create workspace'}</Submit>
      </form>
    </AuthFrame>
  );
}

/** Full-screen states for before the app knows who is signed in. */
export function Splash({ problem, retry }: { problem?: string; retry?: () => void }) {
  return (
    <div className="auth-screen">
      <Aurora />
      <main className="auth-main">
        {problem ? (
          <div className="auth-card auth-card-compact">
            <h1>We can’t reach the server.</h1>
            <p className="auth-sub">{problem}</p>
            <button type="button" className="auth-submit" onClick={retry} data-testid="button-retry">Try again<ArrowRight size={23} /></button>
          </div>
        ) : (
          <div className="auth-loading" role="status" aria-label="Loading"><BrandMark size={72} loop /></div>
        )}
      </main>
    </div>
  );
}

/** Shown when opening an invitation link. */
export function InviteAcceptPage({ token, me }: { token: string; me?: Me | null }) {
  const [, navigate] = useLocation();
  const client = useQueryClient();
  const toast = useToast();
  const invite = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => api.viewInvitation(token),
    retry: false,
  });

  const accept = useMutation({
    mutationFn: () => api.acceptInvitation(token),
    onSuccess: (updatedMe) => {
      client.setQueryData(['me'], updatedMe);
      client.invalidateQueries();
      toast(`Joined ${updatedMe.workspace?.name}!`);
      navigate('/dashboard', { replace: true });
    },
  });

  if (invite.isLoading) return <Splash />;

  if (invite.isError || !invite.data) {
    return (
      <AuthFrame title="Invitation not found" subtitle="This invitation link is invalid or has expired." below={<AuthSwitch question="Have an account?" href="/login" action="Sign in" />}>
        <Notice>Please ask your workspace admin to send you a new invitation link.</Notice>
      </AuthFrame>
    );
  }

  const { workspace_name, inviter_name, role } = invite.data;

  return (
    <AuthFrame
      title={`Join ${workspace_name}`}
      subtitle={`${inviter_name ?? 'A teammate'} has invited you to join the team as ${role === 'admin' || role === 'agent' ? 'an' : 'a'} ${role}.`}
    >
      {me ? (
        <div>
          <Notice tone="info">Signed in as {me.user.email}.</Notice>
          <div style={{ marginTop: '1.25rem' }}>
            <button
              type="button"
              className="auth-submit"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => accept.mutate()}
              disabled={accept.isPending}
            >
              {accept.isPending ? 'Joining…' : `Accept & Join ${workspace_name}`}
            </button>
          </div>
        </div>
      ) : (
        <div>
          <Notice tone="info">Sign in or create an account to accept this invitation.</Notice>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1.25rem' }}>
            <Link href={`/login?next=${encodeURIComponent(`/invite/${token}`)}`} className="auth-submit" style={{ textAlign: 'center', textDecoration: 'none' }}>
              Sign in to accept
            </Link>
            <Link href={`/register?next=${encodeURIComponent(`/invite/${token}`)}`} className="auth-submit" style={{ textAlign: 'center', textDecoration: 'none', background: 'rgba(255,255,255,0.1)' }}>
              Create an account
            </Link>
          </div>
        </div>
      )}
    </AuthFrame>
  );
}

