import type { ReactNode } from 'react';
import { HudCorners } from '@/components/ui/HudCorners';

interface PanelProps {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** Optional short code shown right of the title, e.g. "R-02". */
  code?: string;
}

export function Panel({
  title,
  actions,
  children,
  className = '',
  bodyClassName = 'p-4',
  code,
}: PanelProps) {
  return (
    <section className={`panel flex min-h-0 flex-col ${className}`}>
      <HudCorners />
      <header className="panel-header">
        <h2 className="flex min-w-0 items-center">
          <span className="panel-tick" />
          <span className="panel-title truncate">{title}</span>
          {code && (
            <span className="ml-2 shrink-0 font-mono text-[10px] tracking-widest text-hud/50">
              {code}
            </span>
          )}
        </h2>
        <div className="shrink-0 whitespace-nowrap">{actions}</div>
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
