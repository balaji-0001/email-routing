// Analytics: how much mail, how fast it is answered, what the rules and the AI did.
// Every figure comes from the API, counted from real records.
import { useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'wouter';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AlertTriangle, CheckCircle2, Clock3, Inbox, Send, Sparkles, Workflow } from 'lucide-react';
import { EmptyState, Metric, PageHeading, SkeletonRows } from '@/components/kit';
import { api, type AnalyticsDay } from '@/lib/api';
import { timeAgo } from '@/lib/format';

const RANGES: [number, string][] = [[7, 'Last 7 days'], [30, 'Last 30 days'], [90, 'Last 90 days']];
const shortDay = (day: string) => new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' });
const longDay = (day: string) => new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'long', timeZone: 'UTC' });
const n = (value: number) => value.toLocaleString();

function hours(value: number | null): string {
  if (value === null) return '–';
  if (value < 1) return `${Math.max(1, Math.round(value * 60))} min`;
  return value < 48 ? `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} h` : `${Math.round(value / 24)} days`;
}

type Series = { key: keyof AnalyticsDay; name: string; color: string };

/** One tooltip for every chart: the day, then each series with its swatch. Numbers stay in text colour. */
function Tip({ active, payload, label, series }: { active?: boolean; payload?: { dataKey?: string | number; value?: number }[]; label?: string; series: Series[] }) {
  if (!active || !payload?.length || !label) return null;
  return (
    <div className="viz-tip">
      <b>{longDay(label)}</b>
      {series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.name}<em>{n(Number(payload.find((p) => p.dataKey === s.key)?.value ?? 0))}</em></span>)}
    </div>
  );
}

function Chart({ title, note, data, series, kind, empty }: { title: string; note: string; data: AnalyticsDay[]; series: Series[]; kind: 'line' | 'bar'; empty: string }) {
  const [asTable, setAsTable] = useState(false);
  const nothing = data.every((d) => series.every((s) => !d[s.key]));
  const axis = { tick: { fill: 'var(--viz-muted)', fontSize: 12 }, axisLine: false, tickLine: false } as const;
  const common = { data, margin: { top: 8, right: 12, bottom: 0, left: -12 } };
  // An array, not a fragment: the chart library only recognises these as direct children.
  const frame = [
    <CartesianGrid key="grid" stroke="var(--viz-grid)" vertical={false} />,
    <XAxis key="x" dataKey="day" tickFormatter={shortDay} minTickGap={28} {...axis} />,
    <YAxis key="y" allowDecimals={false} width={52} {...axis} />,
    <Tooltip key="tip" content={<Tip series={series} />} cursor={kind === 'line' ? { stroke: 'var(--viz-muted)', strokeWidth: 1 } : { fill: 'var(--viz-grid)', opacity: 0.5 }} />,
  ];
  return (
    <section className="panel viz-panel" data-testid={`chart-${series[0].key}`}>
      <div className="panel-head">
        <div><h2>{title}</h2><p>{note}</p></div>
        <button type="button" className="viz-toggle" onClick={() => setAsTable(!asTable)} aria-pressed={asTable}>{asTable ? 'Show chart' : 'Show as table'}</button>
      </div>
      {series.length > 1 && <div className="viz-legend">{series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.name}</span>)}</div>}
      {nothing ? <p className="viz-empty">{empty}</p> : asTable ? (
        <div className="data-table-wrap viz-table">
          <table className="data-table"><thead><tr><th>Day</th>{series.map((s) => <th key={s.key}>{s.name}</th>)}</tr></thead>
            <tbody>{[...data].reverse().map((d) => <tr key={d.day}><td>{longDay(d.day)}</td>{series.map((s) => <td key={s.key}>{n(Number(d[s.key]))}</td>)}</tr>)}</tbody></table>
        </div>
      ) : (
        <div className="viz-plot" role="img" aria-label={`${title}. ${series.map((s) => `${s.name}: ${n(data.reduce((sum, d) => sum + Number(d[s.key]), 0))} in total`).join('. ')}.`}>
          <ResponsiveContainer width="100%" height="100%">
            {kind === 'line' ? (
              <LineChart {...common}>{frame}{series.map((s) => <Line key={s.key} type="linear" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: 'var(--viz-surface)', strokeWidth: 2 }} isAnimationActive={false} />)}</LineChart>
            ) : (
              <BarChart {...common} barCategoryGap="22%">{frame}{series.map((s) => <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[4, 4, 0, 0]} maxBarSize={22} isAnimationActive={false} />)}</BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

function Rows({ title, note, head, rows, empty }: { title: string; note: string; head: string[]; rows: (string | number | ReactNode)[][]; empty: string }) {
  return (
    <section className="panel table-panel viz-rows">
      <div className="panel-head"><div><h2>{title}</h2><p>{note}</p></div></div>
      {rows.length === 0 ? <p className="viz-empty">{empty}</p> : (
        <div className="data-table-wrap"><table className="data-table"><thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{typeof cell === 'number' ? n(cell) : cell}</td>)}</tr>)}</tbody></table></div>
      )}
    </section>
  );
}

export function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const report = useQuery({ queryKey: ['analytics', days], queryFn: () => api.analytics(days), refetchInterval: 60000 });
  const r = report.data;
  const period = RANGES.find(([d]) => d === days)![1].toLowerCase();

  return (
    <>
      <PageHeading eyebrow="WORKSPACE" title="Analytics" description="Mail volume, how quickly it is answered, and what rules and AI did. Counted from your real mail, for the mailboxes you can open." />
      <div className="settings-tabs ai-tabs viz-ranges" role="group" aria-label="Period">
        {RANGES.map(([d, label]) => <button key={d} type="button" className={d === days ? 'selected' : ''} onClick={() => setDays(d)} data-testid={`range-${d}`}>{label}</button>)}
      </div>
      {report.isLoading || !r ? <section className="panel"><SkeletonRows rows={5} /></section> : (
        <>
          <div className="metric-grid" data-testid="analytics-tiles">
            <Metric title="Received" value={n(r.totals.received)} delta={`${n(r.totals.sent)} sent`} icon={Inbox} accent="blue" />
            <Metric title="Typical time to reply" value={hours(r.replies.median_hours)} delta={r.replies.count ? `${n(r.replies.within_a_day)} of ${n(r.replies.count)} replies within a day` : 'No replies sent in this period'} icon={Clock3} accent="amber" />
            <Metric title="Open now" value={n(r.now.open)} delta={`${n(r.now.unassigned)} unassigned · ${n(r.now.pending)} pending`} icon={Send} accent="violet" />
            <Metric title="Rule runs" value={n(r.totals.rule_runs)} delta={r.totals.rule_failures ? `${n(r.totals.rule_failures)} failed` : 'None failed'} icon={Workflow} accent="green" />
          </div>

          <Chart title="Mail per day" note={`Emails received and sent, ${period} (days in UTC).`} data={r.daily} kind="line" empty="No mail was received or sent in this period."
            series={[{ key: 'received', name: 'Received', color: 'var(--viz-1)' }, { key: 'sent', name: 'Sent', color: 'var(--viz-2)' }]} />
          <Chart title="Rule runs per day" note={r.totals.rule_failures ? `${n(r.totals.rule_failures)} of ${n(r.totals.rule_runs)} runs failed; see the table below for which rules.` : 'How often rules acted on mail. None failed in this period.'}
            data={r.daily} kind="bar" empty="No rule ran in this period." series={[{ key: 'rule_runs', name: 'Rule runs', color: 'var(--viz-1)' }]} />

          <div className="viz-grid">
            <Rows title="Rules" note="What each rule did in this period." head={['Rule', 'Runs', 'Failed', 'Last ran']} empty="There are no rules yet."
              rows={r.rules.map((rule) => [
                <span key="n" className="viz-name">{rule.failed > 0 ? <AlertTriangle size={14} className="viz-bad" /> : <CheckCircle2 size={14} className="viz-ok" />}{rule.name}{!rule.enabled && <small> (off)</small>}</span>,
                rule.runs, rule.failed, rule.last_run_at ? timeAgo(rule.last_run_at) : 'Never'])} />
            <section className="panel viz-rows" data-testid="analytics-ai">
              <div className="panel-head"><div><h2>AI</h2><p>What the AI did with new mail in this period.</p></div><Link href="/ai" className="activity-link remind-link">Open AI overview</Link></div>
              {r.ai.analysed + r.ai.skipped + r.ai.failed + r.ai.waiting === 0 ? <p className="viz-empty">The AI has not looked at any mail in this period.</p> : (
                <dl className="viz-facts">
                  <div><dt><Sparkles size={14} /> Analysed</dt><dd>{n(r.ai.analysed)}</dd></div>
                  <div><dt>Skipped (automated senders)</dt><dd>{n(r.ai.skipped)}</dd></div>
                  <div><dt>Failed</dt><dd>{n(r.ai.failed)}</dd></div>
                  <div><dt>Needed a reply</dt><dd>{n(r.ai.reply_needed)}</dd></div>
                  <div><dt>Low / Medium / High priority</dt><dd>{n(r.ai.low)} / {n(r.ai.medium)} / {n(r.ai.high)}</dd></div>
                  <div><dt>Replies approved and sent by a person</dt><dd>{n(r.ai.sent_by_people)}</dd></div>
                  <div><dt>Replies sent automatically</dt><dd>{n(r.ai.sent_automatically)}</dd></div>
                  <div><dt>Drafts rejected</dt><dd>{n(r.ai.rejected)}</dd></div>
                  <div><dt>Drafts waiting for approval</dt><dd>{n(r.ai.drafts_waiting)}</dd></div>
                </dl>
              )}
            </section>
            <Rows title="Who writes to you most" note={`Senders by emails received, ${period}.`} head={['Sender', 'Received']} empty="No mail was received in this period."
              rows={r.top_senders.map((s) => [<span key="s" className="viz-name">{s.name || s.email}{s.name && <small> {s.email}</small>}</span>, s.received])} />
            <Rows title="Mailboxes" note={`Mail through each connected mailbox, ${period}.`} head={['Mailbox', 'Received', 'Sent']} empty="No mailbox had mail in this period."
              rows={r.mailboxes.map((m) => [m.email_address, m.received, m.sent])} />
            <Rows title="Workload" note="Open and pending conversations assigned to each person, right now." head={['Person', 'Conversations']} empty="Nothing is assigned to anyone at the moment."
              rows={r.workload.map((w) => [w.name, w.open])} />
            <section className="panel viz-rows">
              <div className="panel-head"><div><h2>Right now</h2><p>Conversations that are not archived or deleted.</p></div></div>
              <dl className="viz-facts">
                <div><dt>Open</dt><dd>{n(r.now.open)}</dd></div>
                <div><dt>Pending</dt><dd>{n(r.now.pending)}</dd></div>
                <div><dt>Closed</dt><dd>{n(r.now.closed)}</dd></div>
                <div><dt>Unread</dt><dd>{n(r.now.unread)}</dd></div>
                <div><dt>Unassigned</dt><dd>{n(r.now.unassigned)}</dd></div>
                <div><dt>Urgent / High priority</dt><dd>{n(r.now.urgent)} / {n(r.now.high)}</dd></div>
              </dl>
            </section>
          </div>
        </>
      )}
      {report.isError && <section className="panel"><EmptyState bare icon={AlertTriangle} title="The figures could not be loaded">Check that the app is running, then reload the page.</EmptyState></section>}
    </>
  );
}
