import type { ReactNode } from 'react';

interface PanelProps {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Panel({
  title,
  actions,
  children,
  className = '',
  bodyClassName = 'px-4 pb-4',
}: PanelProps) {
  return (
    <section className={`panel flex min-h-0 flex-col ${className}`}>
      <header className="panel-header">
        <h2 className="panel-title truncate">{title}</h2>
        {actions && <div className="shrink-0 whitespace-nowrap">{actions}</div>}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
