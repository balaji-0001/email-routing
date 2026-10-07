import { type ReactNode } from 'react';
import { CheckCircle2, X } from 'lucide-react';

type ButtonProps = {
  children: ReactNode;
  onClick: () => void;
  kind?: 'primary' | 'secondary';
  icon?: any;
  testId: string;
  disabled?: boolean;
  ariaLabel?: string;
};

export function Button({
  children,
  onClick,
  kind = 'secondary',
  icon: Icon,
  testId,
  disabled = false,
  ariaLabel,
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`button button-${kind}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      data-testid={testId}
    >
      {Icon && <Icon size={15} />}
      {children}
    </button>
  );
}

export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
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

export function Toast({
  message,
  close,
}: {
  message: string;
  close: () => void;
}) {
  if (!message) return null;
  return (
    <div className="toast-message" role="status" data-testid="status-prototype-message">
      <CheckCircle2 size={17} />
      <span>{message}</span>
      <button
        type="button"
        onClick={close}
        aria-label="Dismiss message"
        data-testid="button-dismiss-message"
      >
        <X size={15} />
      </button>
    </div>
  );
}

export function Field({
  label,
  placeholder,
  type = 'text',
  testId,
}: {
  label: string;
  placeholder?: string;
  type?: string;
  testId: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type={type} placeholder={placeholder} data-testid={testId} />
    </label>
  );
}

export function Metric({
  title,
  value,
  delta,
  icon: Icon,
  accent,
}: {
  title: string;
  value: string;
  delta: string;
  icon: any;
  accent: string;
}) {
  return (
    <div className="metric-card" data-testid={`metric-${title.toLowerCase().replaceAll(' ', '-')}`}>
      <div className={`metric-icon ${accent}`}><Icon size={17} /></div>
      <div className="metric-title">{title}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-delta">{delta}</div>
    </div>
  );
}

export function ActivityItem({
  initials,
  tone,
  text,
  sub,
  time,
}: {
  initials: string;
  tone: string;
  text: ReactNode;
  sub: string;
  time: string;
}) {
  return (
    <div className="activity-item">
      <span className={`avatar avatar-${tone}`}>{initials}</span>
      <div className="activity-text">
        <p>{text}</p>
        <span>{sub}</span>
        <small>{time}</small>
      </div>
    </div>
  );
}
