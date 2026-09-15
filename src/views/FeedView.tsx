import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchObservation, type ObservationPayload } from '@/lib/api';
import { LEAD_TIME_LABELS } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import { SimulatedBanner } from '@/components/layout/SimulatedBanner';
import type { FeedArrival, FeedField, LeadTime, Stamp } from '@/types';

/**
 * The live feed, field by field.
 *
 * Every other view shows what the model made of the data. This one shows the
 * data: which source it came from, when it landed in both UTC and the region's
 * own zone, when the next one is due, the spread of every channel the model is
 * about to read, and the log of arrivals so far. It polls on the region's own
 * cadence rather than the board's, so an arrival appears when it arrives.
 */
export function FeedView() {
  const { regionId, region } = useDashboard();
  const [payload, setPayload] = useState<ObservationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  // Kept in a ref so the countdown below can re-render every second without
  // re-triggering the fetch effect.
  const latest = useRef<ObservationPayload | null>(null);
  latest.current = payload;

  const load = useCallback(
    (signal?: AbortSignal) =>
      fetchObservation(regionId, signal)
        .then((next) => {
          if (signal?.aborted) return;
          setPayload(next);
          setError(null);
        })
        .catch((cause) => {
          if (signal?.aborted) return;
          setError(cause instanceof Error ? cause.message : String(cause));
        }),
    [regionId],
  );

  useEffect(() => {
    setPayload(null);
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, tick]);

  // Poll a few times per cadence so an arrival shows up shortly after it lands,
  // without hammering the API between them.
  useEffect(() => {
    const cadence = region?.cadenceSeconds ?? 600;
    const every = Math.min(30_000, Math.max(3_000, (cadence * 1000) / 4));
    const timer = window.setInterval(() => setTick((n) => n + 1), every);
    return () => window.clearInterval(timer);
  }, [region?.cadenceSeconds]);

  if (error) {
    return (
      <div className="panel p-6">
        <p className="text-[14px] font-semibold text-white">Cannot read the feed</p>
        <p className="mt-2 text-[12px] text-slate-400">{error}</p>
      </div>
    );
  }

  if (!payload) {
    return (
      <div className="panel p-6">
        <p className="text-[13px] text-slate-400">Reading the current observation…</p>
      </div>
    );
  }

  const { observation, fields, arrivals, servedAt, storm } = payload;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {payload.region.simulated && <SimulatedBanner blurb={payload.region.blurb} storm={storm} />}

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <ProvenancePanel payload={payload} servedAt={servedAt} />
        <CountdownPanel
          fetchedAt={observation.timestamp}
          nextUpdate={observation.nextUpdate}
          cadence={observation.cadenceSeconds}
        />
      </div>

      <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <FieldsPanel fields={fields} leadTimes={payload.leadTimes} />
        <ArrivalsPanel arrivals={arrivals} cadence={observation.cadenceSeconds} />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function ProvenancePanel({
  payload,
  servedAt,
}: {
  payload: ObservationPayload;
  servedAt: Stamp;
}) {
  const { observation, region, model } = payload;

  const rows: { label: string; value: string; tone?: 'warn' | 'good' }[] = [
    { label: 'Region', value: `${region.name} · ${region.state}` },
    {
      label: 'Provenance',
      value: region.simulated ? 'Generated — not a measurement' : 'Live upstream observation',
      tone: region.simulated ? 'warn' : 'good',
    },
    { label: 'Source', value: observation.source },
    {
      label: 'Feed state',
      value: observation.degraded ? 'Degraded — fallback in use' : 'Healthy',
      tone: observation.degraded ? 'warn' : 'good',
    },
    {
      label: 'Model',
      value: model.loaded ? `${model.backend} · ${model.runtime}` : 'analytical fallback',
      tone: model.loaded ? 'good' : 'warn',
    },
    { label: 'Grid', value: `${region.rows} × ${region.cols} · ${region.cellCount} cells · 1 km` },
    { label: 'Time zone', value: `${region.timezone} (${observation.timestamp.abbreviation})` },
    { label: 'Served at', value: `${servedAt.localTime} ${servedAt.abbreviation}` },
  ];

  return (
    <Panel title="Feed provenance">
      <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label} className="min-w-0">
            <dt className="text-[11px] text-slate-500">{row.label}</dt>
            <dd
              className={`truncate text-[12px] font-medium ${
                row.tone === 'warn'
                  ? 'text-amber-300'
                  : row.tone === 'good'
                    ? 'text-tier-normal'
                    : 'text-slate-200'
              }`}
              title={row.value}
            >
              {row.value}
            </dd>
          </div>
        ))}
      </dl>

      {observation.notes.length > 0 && (
        // Upstream failures arrive with the whole request URL in them, which is
        // one unbroken token — without `break-words` it runs straight out of
        // the panel and across the next one.
        <ul
          className="mt-3 max-h-32 space-y-1 overflow-y-auto scroll-thin border-t
            border-surface-border pt-2"
        >
          {observation.notes.map((note) => (
            <li
              key={note}
              className="break-words text-[11px] leading-relaxed text-slate-500"
            >
              · {note}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/** Age of the current observation and time until the next one is due. */
function CountdownPanel({
  fetchedAt,
  nextUpdate,
  cadence,
}: {
  fetchedAt: Stamp;
  nextUpdate: Stamp;
  cadence: number;
}) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(id);
  }, []);

  const age = Math.max(0, now - fetchedAt.epoch);
  const due = nextUpdate.epoch - now;
  const progress = Math.min(1, Math.max(0, age / Math.max(cadence, 1)));

  return (
    <Panel title="Timing">
      <div className="grid gap-2 sm:grid-cols-2">
        <StampTile label="Observation valid at" stamp={fetchedAt} />
        <StampTile label="Next update due" stamp={nextUpdate} />
      </div>

      <div className="mt-3">
        <div className="flex items-baseline justify-between text-[11px] text-slate-500">
          <span>Age {formatSeconds(age)}</span>
          <span>
            {due > 0 ? `next in ${formatSeconds(due)}` : 'refresh due'} · cadence{' '}
            {formatSeconds(cadence)}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className={`h-full rounded-full transition-[width] duration-1000 ease-linear ${
              progress >= 1 ? 'bg-tier-warning' : 'bg-accent'
            }`}
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      </div>
    </Panel>
  );
}

function StampTile({ label, stamp }: { label: string; stamp: Stamp }) {
  return (
    <div className="tile">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="mt-1 text-[17px] font-semibold tabular-nums tracking-tight text-white">
        {stamp.localTime}
        <span className="ml-1.5 text-[11px] font-normal text-slate-500">{stamp.abbreviation}</span>
      </p>
      <p className="mt-0.5 text-[10px] tabular-nums text-slate-500">
        {stamp.localDate} · UTC{stamp.utcOffset}
      </p>
      <p className="mt-0.5 truncate text-[10px] tabular-nums text-slate-600" title={stamp.utc}>
        {stamp.utc.replace('T', ' ').slice(0, 19)} UTC
      </p>
    </div>
  );
}

/** Every field in the observation, with units and spread across the grid. */
function FieldsPanel({ fields, leadTimes }: { fields: ObservationPayload['fields']; leadTimes: LeadTime[] }) {
  const [lead, setLead] = useState<LeadTime>(0);

  const groups: { title: string; note: string; rows: FeedField[] }[] = useMemo(
    () => [
      {
        title: 'Observed',
        note: 'served by the upstream feed',
        rows: fields.observed,
      },
      {
        title: 'Derived',
        note: 'computed from the observed fields, Stage 0 formulas',
        rows: fields.derived,
      },
      {
        title: 'Static',
        note: 'read once from the terrain and exposure layers',
        rows: fields.static,
      },
    ],
    [fields],
  );

  return (
    <Panel
      title="Fields in this observation"
      actions={
        <select
          value={lead}
          onChange={(event) => setLead(Number(event.target.value) as LeadTime)}
          className="rounded-[8px] border border-surface-border bg-white/[0.04] px-2 py-1
            text-[11px] text-slate-300 outline-none focus:border-accent"
        >
          {leadTimes.map((value) => (
            <option key={value} value={value} className="bg-surface-deep">
              {LEAD_TIME_LABELS[value] ?? `+${value} min`}
            </option>
          ))}
        </select>
      }
      bodyClassName="min-h-0 flex-1 overflow-y-auto scroll-thin px-4 pb-4"
    >
      <table className="w-full border-collapse text-[12px]">
        <thead className="sticky top-0 bg-surface-raised">
          <tr className="text-left text-[10px] uppercase tracking-wide text-slate-600">
            <th className="py-1.5 pr-2 font-medium">Field</th>
            <th className="py-1.5 pr-2 font-medium">Unit</th>
            <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Min</th>
            <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Mean</th>
            <th className="py-1.5 text-right font-medium tabular-nums">Max</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <FieldGroup key={group.title} group={group} lead={lead} />
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function FieldGroup({
  group,
  lead,
}: {
  group: { title: string; note: string; rows: FeedField[] };
  lead: LeadTime;
}) {
  return (
    <>
      <tr>
        <td colSpan={5} className="pt-3 pb-1">
          <span className="text-[11px] font-semibold text-slate-300">{group.title}</span>
          <span className="ml-2 text-[10px] text-slate-600">{group.note}</span>
        </td>
      </tr>
      {group.rows.map((field) => {
        // Fields that vary with the horizon report per-lead spreads; the rest
        // are single-valued and show the same numbers at every lead.
        const at = field.perLead?.[String(lead)];
        const stats = at ?? field;
        return (
          <tr key={field.key} className="border-t border-surface-border/60">
            <td className="py-1.5 pr-2">
              <span className="font-medium text-slate-200">{field.key}</span>
              {field.modelChannel && (
                <span className="ml-1.5 rounded bg-accent-soft px-1 py-0.5 text-[9px] text-accent">
                  {field.modelChannel}
                </span>
              )}
              {at && (
                <span className="ml-1.5 text-[9px] text-slate-600">
                  {LEAD_TIME_LABELS[lead] ?? `+${lead}m`}
                </span>
              )}
              <p className="mt-0.5 text-[10px] leading-snug text-slate-600">{field.description}</p>
            </td>
            <td className="py-1.5 pr-2 align-top text-[11px] text-slate-500">{field.unit}</td>
            <td className="py-1.5 pr-2 text-right align-top tabular-nums text-slate-400">
              {stats.min}
            </td>
            <td className="py-1.5 pr-2 text-right align-top tabular-nums text-slate-300">
              {stats.mean}
            </td>
            <td className="py-1.5 text-right align-top font-medium tabular-nums text-white">
              {stats.max}
            </td>
          </tr>
        );
      })}
    </>
  );
}

/** The log of observations that have actually landed, newest first. */
function ArrivalsPanel({ arrivals, cadence }: { arrivals: FeedArrival[]; cadence: number }) {
  const newestFirst = useMemo(() => [...arrivals].reverse(), [arrivals]);

  return (
    <Panel
      title="Arrivals"
      actions={
        <span className="text-[11px] text-slate-500">
          {arrivals.length} logged · every {formatSeconds(cadence)}
        </span>
      }
      bodyClassName="min-h-0 flex-1 overflow-y-auto scroll-thin px-2 pb-2"
    >
      {newestFirst.length === 0 ? (
        <p className="px-2 py-6 text-center text-[12px] text-slate-500">
          Nothing logged yet — the first observation appears here when it lands.
        </p>
      ) : (
        <ul className="space-y-1">
          {newestFirst.map((arrival, index) => (
            <li
              key={`${arrival.timestamp.epoch}-${index}`}
              className="rounded-[10px] border border-surface-border bg-white/[0.02] px-2.5 py-2"
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-[12px] font-semibold tabular-nums text-white">
                  {arrival.timestamp.localTime}
                </span>
                <span className="text-[10px] text-slate-600">
                  {arrival.timestamp.abbreviation}
                </span>
                {index === 0 && (
                  <span className="rounded-full bg-tier-normal/20 px-1.5 py-0.5 text-[9px]
                    font-medium text-tier-normal">
                    latest
                  </span>
                )}
                <span className="ml-auto truncate text-[10px] text-slate-500">
                  {arrival.source}
                </span>
                {arrival.simulated && (
                  <span className="rounded-full bg-amber-500/20 px-1.5 py-0.5 text-[9px]
                    font-medium text-amber-300">
                    simulated
                  </span>
                )}
                {arrival.degraded && (
                  <span className="rounded-full bg-tier-warning/20 px-1.5 py-0.5 text-[9px]
                    font-medium text-tier-warning">
                    degraded
                  </span>
                )}
              </div>
              <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] text-slate-500
                sm:grid-cols-4">
                <Metric label="peak rain" value={`${arrival.peakRainRate} mm/hr`} />
                <Metric label="3 hr" value={`${arrival.peakRain3h} mm`} />
                <Metric label="soil" value={`${arrival.peakSoilMoisture}`} />
                <Metric label="cloud" value={`${arrival.meanCloudCover}%`} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <span className="truncate">
      <span className="text-slate-600">{label} </span>
      <span className="tabular-nums text-slate-300">{value}</span>
    </span>
  );
}

function formatSeconds(seconds: number): string {
  const total = Math.round(Math.abs(seconds));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  if (minutes < 60) return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}
