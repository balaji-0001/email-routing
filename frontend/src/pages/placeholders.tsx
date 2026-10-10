// Screens whose feature is not built yet. Each says what will be there and that it is
// not available yet. None of them shows sample data. Everything else in the app is real.
import { useLocation } from 'wouter';
import { Route, Search, Webhook, type LucideIcon } from 'lucide-react';
import { Button, EmptyState, PageHeading } from '@/components/kit';
import { pageDescriptions, pageTitles } from '@/data';

type Placeholder = { icon: LucideIcon; title: string; text: string };

export const PLACEHOLDERS: Record<string, Placeholder> = {
  '/ai/routing': { icon: Route, title: 'Smart routing isn’t available yet', text: 'Suggestions for who is best placed to respond will appear here.' },
  '/webhooks': { icon: Webhook, title: 'No webhooks yet', text: 'Endpoints that receive workspace events will be listed here. Webhooks aren’t available yet.' },
};

function eyebrowFor(path: string): string | undefined {
  if (path.startsWith('/ai')) return 'INTELLIGENCE';
  if (path.startsWith('/automation') || path === '/webhooks') return 'AUTOMATION';
  return undefined;
}

export function PlaceholderBody({ path }: { path: string }) {
  const { icon, title, text } = PLACEHOLDERS[path];
  return <EmptyState icon={icon} title={title}>{text}</EmptyState>;
}

export function PlaceholderPage({ path }: { path: string }) {
  return (
    <>
      <PageHeading eyebrow={eyebrowFor(path)} title={pageTitles[path]} description={pageDescriptions[path]} />
      <PlaceholderBody path={path} />
    </>
  );
}

export function NotFoundPage() {
  const [, navigate] = useLocation();
  return (
    <>
      <PageHeading title="Page not found" description="There is nothing at this address." />
      <EmptyState icon={Search} title="We couldn’t find that page" action={<Button kind="primary" onClick={() => navigate('/dashboard')}>Go to overview</Button>}>Check the address, or head back to the overview.</EmptyState>
    </>
  );
}
