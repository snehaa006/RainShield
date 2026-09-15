import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useDashboard } from '@/hooks/useDashboard';
import { buildCapAlert } from '@/lib/cap';
import { approveAlert, broadcastAlert, cancelAlert, fetchAlerts, resolveAlert } from '@/lib/api';
import type { AlertTier, CapAlert, WardSummary } from '@/types';

export interface AlertEvent {
  id: string;
  createdAt: string;
  updatedAt?: string;
  tier: AlertTier;
  ward: WardSummary;
  cap: CapAlert;
  status: 'UNDER_REVIEW' | 'APPROVED' | 'BROADCASTING' | 'ACTIVE' | 'RESOLVED';
  reason: string[];
  simulation: boolean;
  channels?: Record<string, number>;
}

/**
 * The lifecycle transitions an operator can request. These are named after the
 * backend endpoint they call, not after the status the alert ends up in:
 * `BROADCASTING` lands on ACTIVE server-side once the channels are dispatched.
 * Keeping the map explicit means an unhandled value is a compile error rather
 * than silently falling through to a cancel.
 */
const ALERT_ACTIONS = {
  APPROVED: approveAlert,
  BROADCASTING: broadcastAlert,
  RESOLVED: resolveAlert,
  CANCELLED: cancelAlert,
} as const;

export type AlertAction = keyof typeof ALERT_ACTIONS;

const ALERT_POLL_MS = 2000;

/**
 * The frontend does NOT decide whether an alert exists.
 * FastAPI evaluates every forecast and stores the alert lifecycle. This provider
 * polls that source of truth and turns newly-created records into UI events.
 *
 * It is a provider rather than a plain hook on purpose: AppShell and AlertsView
 * both consume the alert system, and a bare hook gave each of them its own
 * poller, its own seen-id set and its own audio state. One provider means one
 * poll loop and one shared view of the backend's alert store.
 */
function useAlertSystemState() {
  const { wardSummaries, region, isUpdating, isSimulating, lead, selectWard } = useDashboard();
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [newEvent, setNewEvent] = useState<AlertEvent | null>(null);
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [muted, setMuted] = useState(false);
  const seenIds = useRef<Set<string>>(new Set());
  const firstPoll = useRef(true);
  const previousStatus = useRef<Map<string, AlertEvent['status']>>(new Map());

  const playAlarm = useCallback(() => {
    if (!audioEnabled || muted) return;
    try {
      const AudioContextCtor =
        window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioContextCtor) return;

      const ctx = new AudioContextCtor();
      void ctx.resume();
      const now = ctx.currentTime;
      [0, 0.24, 0.48, 0.72].forEach((offset, index) => {
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.value = index % 2 === 0 ? 880 : 660;
        gain.gain.setValueAtTime(0.0001, now + offset);
        gain.gain.exponentialRampToValueAtTime(0.20, now + offset + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.18);
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.start(now + offset);
        oscillator.stop(now + offset + 0.2);
      });
      window.setTimeout(() => void ctx.close(), 1200);
    } catch {
      // Visual alerting must continue even if browser audio is unavailable.
    }
  }, [audioEnabled, muted]);

  const enableAudio = useCallback(async () => {
    try {
      const AudioContextCtor =
        window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (AudioContextCtor) {
        const ctx = new AudioContextCtor();
        await ctx.resume();
        // Short confirmation chirp while this is still a user gesture.
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        oscillator.frequency.value = 660;
        gain.gain.value = 0.04;
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.start();
        oscillator.stop(ctx.currentTime + 0.12);
        window.setTimeout(() => void ctx.close(), 250);
      }
      setAudioEnabled(true);
    } catch {
      // Keep the visual alarm available even if the browser blocks audio.
      setAudioEnabled(true);
    }
  }, []);

  const hydrate = useCallback(async () => {
    if (!region?.id || wardSummaries.length === 0) return;

    try {
      const payload = await fetchAlerts(region.id);
      const localByWard = new Map(wardSummaries.map((ward) => [ward.ward.id, ward]));
      const nextEvents: AlertEvent[] = [];

      for (const record of payload.alerts) {
        if (record.status === 'CANCELLED') continue;
        const ward = localByWard.get(record.ward.id);
        if (!ward) continue;

        const event: AlertEvent = {
          id: record.id,
          createdAt: record.createdAt,
          updatedAt: record.updatedAt,
          tier: record.tier,
          ward,
          cap: buildCapAlert(ward, region),
          status: record.status,
          reason: record.reason,
          simulation: record.simulation,
          channels: record.channels,
        };
        nextEvents.push(event);

        const oldStatus = previousStatus.current.get(record.id);
        const isNew = !seenIds.current.has(record.id);
        const becameActive = oldStatus && oldStatus !== record.status && record.status === 'ACTIVE';

        // Do not throw a giant overlay on initial page load for an old alert.
        // Only newly-created backend records trigger the emergency overlay.
        if (!firstPoll.current && isNew && record.status === 'UNDER_REVIEW') {
          setNewEvent(event);
          selectWard(ward.ward.id);
          playAlarm();
        } else if (becameActive && record.status === 'ACTIVE') {
          // Keep the command center state synchronized without re-opening the modal.
          selectWard(ward.ward.id);
        }

        seenIds.current.add(record.id);
        previousStatus.current.set(record.id, record.status);
      }

      nextEvents.sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
      setEvents(nextEvents.slice(0, 20));
      firstPoll.current = false;
    } catch {
      // Forecast/dashboard errors should not take down the alert UI. The next
      // poll retries automatically.
    }
  }, [region, wardSummaries, playAlarm, selectWard]);

  // Fetch immediately whenever the active forecast/what-if state changes.
  useEffect(() => {
    void hydrate();
  }, [hydrate, isUpdating, isSimulating]);

  // Poll independently so a backend-created alert becomes visible even when
  // the user is sitting on the dashboard or Alerts page.
  useEffect(() => {
    const timer = window.setInterval(() => void hydrate(), ALERT_POLL_MS);
    return () => window.clearInterval(timer);
  }, [hydrate]);

  const clearNewEvent = useCallback(() => setNewEvent(null), []);

  const updateStatus = useCallback(
    (id: string, action: AlertAction) => {
      // Re-hydrate either way: on success to pick up the new status, on failure
      // to resynchronise with whatever the backend actually holds.
      void ALERT_ACTIONS[action](id)
        .then(() => hydrate())
        .catch(() => hydrate());
    },
    [hydrate],
  );

  const activeEvent = useMemo(
    () => events.find((event) => event.status !== 'RESOLVED') ?? null,
    [events],
  );
  const criticalEvents = useMemo(
    () => events.filter((event) => event.tier === 'CRITICAL' && event.status !== 'RESOLVED'),
    [events],
  );

  return useMemo(
    () => ({
      events,
      activeEvent,
      criticalEvents,
      newEvent,
      clearNewEvent,
      updateStatus,
      audioEnabled,
      enableAudio,
      muted,
      setMuted,
      isUpdating,
      isSimulating,
      lead,
    }),
    [
      events,
      activeEvent,
      criticalEvents,
      newEvent,
      clearNewEvent,
      updateStatus,
      audioEnabled,
      enableAudio,
      muted,
      isUpdating,
      isSimulating,
      lead,
    ],
  );
}

type AlertSystemValue = ReturnType<typeof useAlertSystemState>;

const AlertSystemContext = createContext<AlertSystemValue | null>(null);

export function AlertSystemProvider({ children }: { children: ReactNode }) {
  const value = useAlertSystemState();
  return <AlertSystemContext.Provider value={value}>{children}</AlertSystemContext.Provider>;
}

export function useAlertSystem(): AlertSystemValue {
  const value = useContext(AlertSystemContext);
  if (!value) throw new Error('useAlertSystem must be used inside <AlertSystemProvider>');
  return value;
}
