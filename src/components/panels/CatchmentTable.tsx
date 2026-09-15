/**
 * Every catchment's balance, as a table.
 *
 * The two columns that carry the argument are `rain` and `clears` — the
 * intensity falling against the intensity the current supply can remove. When
 * the first exceeds the second the catchment is accumulating water, and the
 * deficit and pump count follow from that. Putting them side by side makes the
 * comparison readable without doing arithmetic on cumecs.
 *
 * The unpumped remainder is rendered below a rule and deliberately without a
 * verdict: no capacity was ever modelled for it, so a deficit there would be
 * an invented number.
 */

import type { CatchmentBalance } from '@/types';

const SUFFICIENT = '#22c55e';
const SHORT = '#ef4444';

export function CatchmentTable({
  catchments,
  unpumped,
  pumpUnitCumecs,
}: {
  catchments: CatchmentBalance[];
  unpumped: CatchmentBalance | null;
  pumpUnitCumecs: number;
}) {
  return (
    <table className="w-full min-w-[640px] border-collapse text-[12px]">
      <thead>
        <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
          <th className="pb-2 pr-3 font-medium">Catchment</th>
          <th className="pb-2 pr-3 text-right font-medium">km²</th>
          <th className="pb-2 pr-3 text-right font-medium">Rain</th>
          <th className="pb-2 pr-3 text-right font-medium">Clears</th>
          <th className="pb-2 pr-3 text-right font-medium">Inflow</th>
          <th className="pb-2 pr-3 text-right font-medium">Supply</th>
          <th className="pb-2 pr-3 text-right font-medium">Deficit</th>
          <th className="pb-2 text-right font-medium">Needs</th>
        </tr>
      </thead>
      <tbody>
        {catchments.map((c) => (
          <tr key={c.id} className="border-t border-white/[0.06]">
            <td className="py-1.5 pr-3">
              <span className="text-slate-200">{c.name}</span>
              {c.gateClosed && (
                <span className="ml-1.5 rounded bg-amber-500/15 px-1 py-px text-[10px] text-amber-300">
                  gate shut
                </span>
              )}
            </td>
            <td className="py-1.5 pr-3 text-right tabular-nums text-slate-400">
              {c.areaKm2.toFixed(2)}
            </td>
            <td className="py-1.5 pr-3 text-right tabular-nums text-slate-200">
              {c.rainfallMmHr.toFixed(1)}
            </td>
            <td
              className="py-1.5 pr-3 text-right tabular-nums"
              style={{ color: c.sufficient ? SUFFICIENT : SHORT }}
            >
              {c.capacityMmHr.toFixed(0)}
            </td>
            <td className="py-1.5 pr-3 text-right tabular-nums text-slate-400">
              {c.inflowCumecs.toFixed(1)}
            </td>
            <td className="py-1.5 pr-3 text-right tabular-nums text-slate-400">
              {c.supplyCumecs.toFixed(1)}
            </td>
            <td
              className="py-1.5 pr-3 text-right tabular-nums"
              style={{ color: c.deficitCumecs > 0 ? SHORT : '#64748b' }}
            >
              {c.deficitCumecs > 0 ? `+${c.deficitCumecs.toFixed(1)}` : '—'}
            </td>
            <td className="py-1.5 text-right tabular-nums text-slate-200">
              {c.extraPumpsRequired > 0 ? `${c.extraPumpsRequired} pumps` : '—'}
            </td>
          </tr>
        ))}

        {unpumped && (
          <tr className="border-t-2 border-white/[0.12] text-slate-500">
            <td className="py-1.5 pr-3">{unpumped.name}</td>
            <td className="py-1.5 pr-3 text-right tabular-nums">{unpumped.areaKm2.toFixed(0)}</td>
            <td className="py-1.5 pr-3 text-right tabular-nums">
              {unpumped.rainfallMmHr.toFixed(1)}
            </td>
            <td className="py-1.5 pr-3 text-right">—</td>
            <td className="py-1.5 pr-3 text-right tabular-nums">
              {unpumped.inflowCumecs.toFixed(0)}
            </td>
            <td className="py-1.5 pr-3 text-right" colSpan={3}>
              capacity not modelled
            </td>
          </tr>
        )}
      </tbody>
      <tfoot>
        <tr>
          <td colSpan={8} className="pt-3 text-[10px] leading-relaxed text-slate-600">
            <strong className="font-medium text-slate-500">Rain</strong> and{' '}
            <strong className="font-medium text-slate-500">Clears</strong> are both mm/hr — what
            is falling against what the current supply removes. Inflow, supply and deficit are
            m³/s. A pump is {pumpUnitCumecs.toFixed(0)} m³/s.
          </td>
        </tr>
      </tfoot>
    </table>
  );
}
