import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, CircleAlert, X, type LucideIcon } from 'lucide-react';
import { initials } from '@/lib/format';

// --- toasts ---------------------------------------------------------------

type Tone = 'success' | 'error';
type ToastState = { id: number; message: string; tone: Tone };

const ToastContext = createContext<(message: string, tone?: Tone) => void>(() => {});

/** `const toast = useToast(); toast('Saved')` shows a short message that dismisses itself. */
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const show = useCallback((message: string, tone: Tone = 'success') => setToast({ id: Date.now(), message, tone }), []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), toast.tone === 'error' ? 8000 : 5000);
    return () => clearTimeout(timer);
  }, [toast]);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <AnimatePresence>
        {toast && (
          <motion.div
            key={toast.id}
            className={`toast-message ${toast.tone}`}
            role={toast.tone === 'error' ? 'alert' : 'status'}
            initial={{ opacity: 0, y: 14, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
            data-testid="toast"
          >
            {toast.tone === 'error' ? <CircleAlert size={20} /> : <CheckCircle2 size={20} />}
            <span>{toast.message}</span>
            <button type="button" onClick={() => setToast(null)} aria-label="Dismiss message"><X size={17} /></button>
          </motion.div>
        )}
      </AnimatePresence>
    </ToastContext.Provider>
  );
}

// --- building blocks ------------------------------------------------------

export function Button({ children, onClick, kind = 'secondary', icon: Icon, disabled = false, type = 'button', testId }: {
  children: ReactNode;
  onClick?: () => void;
  kind?: 'primary' | 'secondary';
  icon?: LucideIcon;
  disabled?: boolean;
  type?: 'button' | 'submit';
  testId?: string;
}) {
  return (
    <button type={type} className={`button button-${kind}`} onClick={onClick} disabled={disabled} data-testid={testId}>
      {Icon && <Icon size={17} />}
      {children}
    </button>
  );
}

export function PageHeading({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}

/** What a screen shows when there is nothing real to list yet. */
export function EmptyState({ icon: Icon, title, children, action, bare = false }: { icon: LucideIcon; title: string; children?: ReactNode; action?: ReactNode; bare?: boolean }) {
  const body = (
    <div className="empty-state" data-testid="empty-state">
      <div className="empty-icon"><Icon size={24} /></div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
  return bare ? body : <section className="panel">{body}</section>;
}

export function Metric({ title, value, delta, icon: Icon, accent }: { title: string; value: string; delta: string; icon: LucideIcon; accent: 'blue' | 'amber' | 'green' | 'violet' }) {
  return (
    <div className="metric-card" data-testid={`metric-${title.toLowerCase().replaceAll(' ', '-')}`}>
      <div className={`metric-icon ${accent}`}><Icon size={20} /></div>
      <div className="metric-title">{title}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-delta">{delta}</div>
    </div>
  );
}

const TONES = ['blue', 'peach', 'mint', 'lavender'];

/** Initials on a colour that stays the same for the same person. */
export function Avatar({ name, className = '' }: { name: string; className?: string }) {
  const tone = TONES[[...name].reduce((sum, char) => sum + char.charCodeAt(0), 0) % TONES.length];
  return <span className={`avatar avatar-${tone} ${className}`}>{initials(name)}</span>;
}

export function Field({ label, value, onChange, type = 'text', placeholder, error, hint, readOnly = false, autoComplete, testId }: {
  label: string;
  value: string;
  onChange?: (value: string) => void;
  type?: string;
  placeholder?: string;
  error?: string;
  hint?: string;
  readOnly?: boolean;
  autoComplete?: string;
  testId?: string;
}) {
  return (
    <label className={`field ${error ? 'field-invalid' : ''}`}>
      <span>{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        placeholder={placeholder}
        readOnly={readOnly}
        autoComplete={autoComplete}
        aria-invalid={!!error}
        data-testid={testId ?? `input-${label.toLowerCase().replaceAll(' ', '-')}`}
      />
      {error ? <small className="field-error" role="alert">{error}</small> : hint && <small className="field-hint">{hint}</small>}
    </label>
  );
}

export function SelectField({ label, value, onChange, options, error, disabled = false, testId }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  error?: string;
  disabled?: boolean;
  testId?: string;
}) {
  return (
    <label className={`field ${error ? 'field-invalid' : ''}`}>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} data-testid={testId}>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
      {error && <small className="field-error" role="alert">{error}</small>}
    </label>
  );
}

export function Switch({ on, onChange, label, disabled = false, testId }: { on: boolean; onChange: (on: boolean) => void; label: string; disabled?: boolean; testId?: string }) {
  return (
    <button type="button" className={`switch ${on ? 'on' : ''}`} role="switch" aria-checked={on} aria-label={label} disabled={disabled} onClick={() => onChange(!on)} data-testid={testId}>
      <i />
    </button>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="sk-list" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div className="sk-row" key={i}><span className="sk sk-dot" /><div><span className="sk sk-line sk-w30" /><span className="sk sk-line sk-w80" /></div></div>
      ))}
    </div>
  );
}
