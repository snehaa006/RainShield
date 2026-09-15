import { TIER_LABELS } from '@/lib/config';
import { duration, metres, percent } from '@/lib/format';
import type { AlertTier, CapAlert, RegionDescriptor, WardSummary } from '@/types';

const SEVERITY: Record<AlertTier, CapAlert['severity']> = {
  NORMAL: 'Minor',
  WATCH: 'Moderate',
  WARNING: 'Severe',
  CRITICAL: 'Extreme',
};

const URGENCY: Record<AlertTier, CapAlert['urgency']> = {
  NORMAL: 'Future',
  WATCH: 'Future',
  WARNING: 'Expected',
  CRITICAL: 'Immediate',
};

const INSTRUCTIONS: Record<AlertTier, string> = {
  NORMAL: 'No action required. Continue routine monitoring of drainage and gauge levels.',
  WATCH:
    'Pre-position pumping crews, clear storm-water inlets and brief ward-level response teams.',
  WARNING:
    'Avoid low-lying roads and underpasses. Move vehicles to higher ground and prepare shelters for activation.',
  CRITICAL:
    'Evacuate low-lying pockets immediately. Activate relief shelters, close flooded underpasses and deploy rescue teams.',
};

/**
 * Build a CAP 1.2 payload from the warning engine's ward-level output.
 *
 * `status` is Exercise for a live region and stays Exercise for a simulated
 * one — but a simulated region also says so in the area description, so an
 * alert lifted out of the UI cannot be mistaken for a real place.
 */
export function buildCapAlert(
  ward: WardSummary,
  region: RegionDescriptor | null,
  sentAt = new Date(),
): CapAlert {
  const certainty =
    ward.confidence === 'HIGH' ? 'Likely' : ward.confidence === 'MEDIUM' ? 'Possible' : 'Possible';

  return {
    identifier:
      `RAINSHIELD-${(region?.state ?? 'XX').slice(0, 2).toUpperCase()}` +
      `-${ward.ward.id.toUpperCase()}-${sentAt.getTime()}`,
    sent: sentAt.toISOString(),
    status: 'Exercise',
    msgType: 'Alert',
    scope: 'Public',
    severity: SEVERITY[ward.tier],
    urgency: URGENCY[ward.tier],
    certainty,
    event: 'Urban Flooding / Heavy Rainfall',
    headline: `${TIER_LABELS[ward.tier].toUpperCase()}: urban flooding expected in ${ward.ward.name}`,
    description:
      `Flood probability ${percent(ward.peakFloodProbability)} with expected water depth up to ` +
      `${metres(ward.peakWaterDepth)}. Estimated onset in ${duration(ward.timeToInundation)}. ` +
      `Ensemble confidence: ${ward.confidence.toLowerCase()}.`,
    instruction: INSTRUCTIONS[ward.tier],
    areaDesc:
      `${ward.ward.name}, ${region?.name ?? 'unknown region'}, ${region?.state ?? ''}` +
      (region?.simulated ? ' [SIMULATED — not a real place]' : ''),
    expires: new Date(sentAt.getTime() + 6 * 3600_000).toISOString(),
  };
}

/** Serialise a CAP payload to the XML disaster-management authorities ingest. */
export function capToXml(alert: CapAlert): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>${alert.identifier}</identifier>
  <sender>rainshield.ai</sender>
  <sent>${alert.sent}</sent>
  <status>${alert.status}</status>
  <msgType>${alert.msgType}</msgType>
  <scope>${alert.scope}</scope>
  <info>
    <category>Met</category>
    <event>${alert.event}</event>
    <urgency>${alert.urgency}</urgency>
    <severity>${alert.severity}</severity>
    <certainty>${alert.certainty}</certainty>
    <expires>${alert.expires}</expires>
    <headline>${escapeXml(alert.headline)}</headline>
    <description>${escapeXml(alert.description)}</description>
    <instruction>${escapeXml(alert.instruction)}</instruction>
    <area>
      <areaDesc>${escapeXml(alert.areaDesc)}</areaDesc>
    </area>
  </info>
</alert>`;
}

function escapeXml(value: string): string {
  return value.replace(/[<>&'"]/g, (char) => {
    switch (char) {
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '&':
        return '&amp;';
      case "'":
        return '&apos;';
      default:
        return '&quot;';
    }
  });
}
