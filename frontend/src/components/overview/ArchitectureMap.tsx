import { useQuery } from '@tanstack/react-query';
import { ExternalLink } from 'lucide-react';
import { fetchSymbols } from '../../api/symbols';
import type { SymbolListItem } from '../../api/symbols';

interface ArchitectureMapProps {
  repoId: number;
  apiBase?: string;
  onOpenFullGraph?: () => void;
  onSelectModule?: (moduleName: string) => void;
  onInspectSymbols?: (moduleName: string) => void;
  onInspectSymbolDetail?: (symbolId: number) => void;
}

export default function ArchitectureMap({
  repoId,
  apiBase,
  onOpenFullGraph,
  onSelectModule,
  onInspectSymbols,
  onInspectSymbolDetail,
}: ArchitectureMapProps) {
  const symbolsQuery = useQuery({
    queryKey: ['architecture-symbols', repoId, apiBase ?? 'default'],
    queryFn: ({ signal }) => fetchSymbols({ repoId, query: '', limit: 100, signal, apiBase }),
    retry: false,
  });
  const files = new Map<string, SymbolListItem[]>();
  for (const symbol of symbolsQuery.data?.symbols ?? []) {
    const current = files.get(symbol.file_path) ?? [];
    current.push(symbol);
    files.set(symbol.file_path, current);
  }

  return (
    <section className="reposcope-architecture-map" aria-labelledby="architecture-map-heading">
      <header className="reposcope-section-header">
        <div>
          <h2 id="architecture-map-heading" className="reposcope-section-title">Indexed architecture</h2>
          <p className="reposcope-section-subtitle">Live files and symbols from the repository index.</p>
        </div>
        <button type="button" className="reposcope-inline-link-btn" onClick={onOpenFullGraph}>
          Open dependency graph <ExternalLink size={13} />
        </button>
      </header>
      {symbolsQuery.isPending && <p className="reposcope-content-state">Loading indexed symbols…</p>}
      {symbolsQuery.isError && <p role="alert" className="reposcope-content-state">{symbolsQuery.error.message}</p>}
      {!symbolsQuery.isPending && !symbolsQuery.isError && files.size === 0 && (
        <p className="reposcope-content-state">No indexed symbols are available.</p>
      )}
      <div className="reposcope-architecture-list">
        {[...files.entries()].map(([path, symbols]) => (
          <div key={path} className="reposcope-architecture-module" onClick={() => onSelectModule?.(path)}>
            <button type="button" className="reposcope-inline-link-btn" onClick={() => onInspectSymbols?.(path)}>
              {path} ({symbols.length})
            </button>
            <div>
              {symbols.slice(0, 5).map((symbol) => (
                <button key={symbol.id} type="button" className="reposcope-inline-link-btn" onClick={() => onInspectSymbolDetail?.(symbol.id)}>
                  {symbol.qualname}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
