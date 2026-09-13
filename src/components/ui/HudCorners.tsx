/**
 * L-shaped bracket accents that frame a panel or the map, as on the reference
 * command boards. The top-right corner is left bare because the panel shape
 * already carries a diagonal notch there.
 */
export function HudCorners({ className = '' }: { className?: string }) {
  return (
    <span aria-hidden className={`pointer-events-none absolute inset-0 z-10 ${className}`}>
      <span className="hud-corner left-0 top-0 border-l border-t" />
      <span className="hud-corner bottom-0 left-0 border-b border-l" />
      <span className="hud-corner bottom-0 right-0 border-b border-r" />
    </span>
  );
}
