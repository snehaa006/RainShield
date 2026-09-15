/**
 * Drainage and pumping — the Stage A mass balance, on screen.
 *
 * The question this view exists to answer is the one a reviewer actually
 * asks: given the rain that is falling, how much pumping capacity does the
 * city need, does it have it, and if not, what more? Everything here is a
 * volumetric balance — rain in, gravity and pumps out — rather than anything
 * the neural network has an opinion about. Nothing on this page feeds back
 * into the risk scores.
 *
 * The tide control is the centrepiece rather than a garnish. Mumbai's gravity
 * outfalls shut when the sea rises above their inverts, so the answer flips
 * between low and high water, and dragging the slider is the fastest way to
 * see that a network which copes at low tide does not cope at high.
 */

import { useCallback, useEffect, useState } from 'react';
import { ApiError, fetchDrainage, type DrainagePayload } from '@/lib/api';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import { Meter } from '@/components/ui/Meter';
import { Slider } from '@/components/ui/Slider';
import { TideDial } from '@/components/panels/TideDial';
import { CatchmentTable } from '@/components/panels/CatchmentTable';
import type { CatchmentBalance } from '@/types';

const SUFFICIENT = '#22c55e';
const SHORT = '#ef4444';

export function DrainageView() {
  const { lead, whatIf, regionId } = useDashboard();
  const [payload, setPayload] = useState<DrainagePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tide, setTide] = useState<number | null>(null);
  const [availability, setAvailability] = useState(1);

  // Pinning the tide is per-region: chart datum means something different on
  // each coast, so a level dragged for one is meaningless on the other.
  useEffect(() => setTide(null), [regionId]);

  useEffect(() => {
    const controller = new AbortController();
    fetchDrainage(lead, whatIf, regionId, tide, availability, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) {
          setPayload(next);
          setError(null);
        }
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
      });
    return () => controller.abort();
  }, [lead, whatIf, regionId, tide, availability]);

  const resetTide = useCallback(() => setTide(null), []);

  if (error) {
    return (
      <Panel title="Drainage and pumping">
        <p className="text-[12px] leading-relaxed text-rose-300">{error}</p>
      </Panel>
    );
  }

  if (!payload) {
    return (
      <Panel title="Drainage and pumping">
        <p className="text-[12px] text-slate-500">Assessing catchments…</p>
      </Panel>
    );
  }

  const { totals, tide: tideState } = payload;
  const sufficient = totals.sufficient;

  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex min-h-0 flex-col gap-3">
        <Panel title="Can the network keep up?">
          <Verdict payload={payload} />
        </Panel>

        <Panel title="Catchments" bodyClassName="px-4 pb-4 overflow-x-auto scroll-thin">
          <CatchmentTable
            catchments={payload.catchments}
            unpumped={payload.unpumped}
            pumpUnitCumecs={totals.pumpUnitCumecs}
          />
        </Panel>

        <Panel title="What this model can be read to say">
          <p className="text-[11px] leading-relaxed text-slate-400">{payload.caveat}</p>
        </Panel>
      </div>

      <div className="flex min-h-0 flex-col gap-3">
        <Panel
          title="Tide"
          actions={
            payload.tideOverridden ? (
              <button
                type="button"
                onClick={resetTide}
                className="rounded-full bg-white/[0.08] px-2.5 py-1 text-[11px] text-slate-300
                  transition hover:bg-white/[0.14]"
              >
                Use prediction
              </button>
            ) : (
              <span className="text-[11px] text-slate-500">predicted</span>
            )
          }
        >
          <TideDial tide={tideState} overridden={payload.tideOverridden} />

          <div className="mt-4">
            <Slider
              label="Sea level"
              min={Math.floor(tideState.lowestAstronomicalMCd * 10) / 10}
              max={Math.ceil(tideState.highestAstronomicalMCd * 10) / 10}
              step={0.1}
              value={tide ?? tideState.levelMCd}
              display={`${(tide ?? tideState.levelMCd).toFixed(2)} m CD`}
              onChange={setTide}
              hint={
                sufficient
                  ? 'Drag towards high water. Gravity outfalls shut above their inverts, and the answer changes.'
                  : 'Drag towards low water to see how much of the shortfall is the tide rather than the rain.'
              }
            />
          </div>

          <p className="mt-3 text-[11px] leading-relaxed text-slate-500">{tideState.basis}</p>
        </Panel>

        <Panel title="Pump availability">
          <Slider
            label="Capacity running"
            min={0}
            max={1}
            step={0.05}
            value={availability}
            display={`${Math.round(availability * 100)}%`}
            onChange={setAvailability}
            hint="What a station out of service would cost, before the rain arrives."
          />
          <div className="mt-4 space-y-3">
            <Meter
              label="Installed capacity"
              value={1}
              display={`${totals.installedPumpCumecs.toFixed(0)} m³/s`}
              color="#0a84ff"
              hint={`${payload.stations.length} stations, ${totals.designIntensityMmHr.toFixed(0)} mm/hr design standard`}
            />
            <Meter
              label="Available now"
              value={
                totals.installedPumpCumecs > 0
                  ? totals.supplyCumecs / Math.max(totals.installedPumpCumecs, 1)
                  : 0
              }
              display={`${totals.supplyCumecs.toFixed(0)} m³/s`}
              color={sufficient ? SUFFICIENT : SHORT}
              hint={
                payload.catchments.every((c) => c.gateClosed)
                  ? 'Every gravity gate is shut — pumps only.'
                  : 'Gravity outfalls are contributing.'
              }
            />
          </div>
        </Panel>

        <Panel title="Stations">
          <StationList stations={payload.stations} catchments={payload.catchments} />
        </Panel>
      </div>
    </div>
  );
}

/** The headline: sufficient or not, and what would close the gap. */
function Verdict({ payload }: { payload: DrainagePayload }) {
  const { totals } = payload;
  const gatesShut = payload.catchments.filter((c) => c.gateClosed).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          className="text-[19px] font-semibold"
          style={{ color: totals.sufficient ? SUFFICIENT : SHORT }}
        >
          {totals.sufficient ? 'Capacity is sufficient' : 'Capacity is short'}
        </span>
        <span className="text-[12px] text-slate-400">
          across {totals.catchmentCount} pumped catchment
          {totals.catchmentCount === 1 ? '' : 's'}
        </span>
      </div>

      {!totals.sufficient && (
        <p className="text-[13px] leading-relaxed text-slate-300">
          {totals.catchmentsInDeficit} of {totals.catchmentCount} catchments cannot clear what
          is arriving. Closing every shortfall needs{' '}
          <strong className="font-semibold text-white">
            {totals.extraPumpsRequired} more pump
            {totals.extraPumpsRequired === 1 ? '' : 's'} of{' '}
            {totals.pumpUnitCumecs.toFixed(0)} m³/s
          </strong>{' '}
          — {totals.deficitCumecs.toFixed(1)} m³/s of unmet lift.
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Figure label="Inflow" value={`${payload.totals.inflowCumecs.toFixed(1)}`} unit="m³/s" />
        <Figure label="Supply" value={`${totals.supplyCumecs.toFixed(1)}`} unit="m³/s" />
        <Figure
          label="Deficit"
          value={totals.deficitCumecs.toFixed(1)}
          unit="m³/s"
          tone={totals.deficitCumecs > 0 ? SHORT : SUFFICIENT}
        />
        <Figure
          label="Gates shut"
          value={`${gatesShut}/${totals.catchmentCount}`}
          unit={payload.tide.phase}
        />
      </div>

      <p className="text-[11px] leading-relaxed text-slate-500">
        Deficits are summed per catchment, not netted: spare capacity at one outfall cannot
        drain another&rsquo;s water.
      </p>
    </div>
  );
}

function Figure({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: string;
  unit: string;
  tone?: string;
}) {
  return (
    <div className="rounded-lg bg-white/[0.04] px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div
        className="mt-0.5 text-[17px] font-semibold tabular-nums"
        style={{ color: tone ?? '#fff' }}
      >
        {value}
      </div>
      <div className="text-[10px] text-slate-500">{unit}</div>
    </div>
  );
}

function StationList({
  stations,
  catchments,
}: {
  stations: DrainagePayload['stations'];
  catchments: CatchmentBalance[];
}) {
  const byId = new Map(catchments.map((c) => [c.stationId, c]));

  return (
    <ul className="space-y-2.5">
      {stations.map((station) => {
        const catchment = byId.get(station.id);
        const short = catchment ? !catchment.sufficient : false;
        return (
          <li key={station.id} className="rounded-lg bg-white/[0.04] px-3 py-2">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[12px] font-medium text-white">{station.name}</span>
              <span
                className="shrink-0 text-[12px] font-semibold tabular-nums"
                style={{ color: short ? SHORT : SUFFICIENT }}
              >
                {station.capacityCumecs.toFixed(0)} m³/s
              </span>
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {station.pumps} pumps · invert {station.outfallInvertMCd.toFixed(1)} m CD
              {station.commissioned ? ` · ${station.commissioned}` : ''}
              {catchment?.gateClosed ? ' · gate shut' : ''}
            </div>
          </li>
        );
      })}
      <li className="pt-1 text-[10px] leading-relaxed text-slate-600">
        {stations[0]?.capacityBasis}
      </li>
    </ul>
  );
}
