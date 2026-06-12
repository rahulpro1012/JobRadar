import { Filter, Ban, ChevronDown, ChevronUp, EyeOff, Eye, Mail } from 'lucide-react';
import { useState } from 'react';
import { sourceName } from '../utils/helpers';

const DATE_OPTIONS = [
  { value: 1, label: 'Today' },
  { value: 3, label: 'Last 3 days' },
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 0, label: 'All time' },
];

export default function Sidebar({
  filters, onFilterChange, blacklistCount, onManageBlacklist,
  showDismissed = false, onToggleDismissed, dismissedCount = 0,
  availableSources = {},
}) {
  const [showFilters, setShowFilters] = useState(true);

  // Data-driven source list from actual jobs (stats.by_source), most jobs first
  const sources = Object.entries(availableSources)
    .filter(([domain]) => domain)
    .sort((a, b) => b[1] - a[1])
    .map(([domain, count]) => ({ key: domain, label: sourceName(domain), count }));

  const handleSourceToggle = (sourceKey) => {
    const current = filters.sources || [];
    const updated = current.includes(sourceKey)
      ? current.filter((s) => s !== sourceKey) : [...current, sourceKey];
    onFilterChange({ ...filters, sources: updated });
  };

  return (
    <aside className="w-full lg:w-64 shrink-0">
      <div className="card p-4 space-y-5">
        <button onClick={() => setShowFilters(!showFilters)} className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2 text-sm font-semibold t-secondary">
            <Filter className="w-4 h-4 text-brand-500" /> Filters
          </div>
          {showFilters ? <ChevronUp className="w-4 h-4 t-faint" /> : <ChevronDown className="w-4 h-4 t-faint" />}
        </button>

        {showFilters && (
          <>
            {/* Email-only toggle */}
            <label className="flex items-center gap-2 cursor-pointer text-sm t-muted hover:t-primary">
              <input type="checkbox" checked={!!filters.viaEmail}
                onChange={() => onFilterChange({ ...filters, viaEmail: !filters.viaEmail })}
                className="rounded text-brand-500 focus:ring-brand-500/30" />
              <Mail className="w-3.5 h-3.5 text-brand-500" />
              <span>From email alerts only</span>
            </label>

            {sources.length > 0 && (
              <div>
                <p className="text-xs font-medium t-faint uppercase tracking-wider mb-2">Source</p>
                <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                  {sources.map((src) => (
                    <label key={src.key} className="flex items-center gap-2 cursor-pointer text-sm t-muted hover:t-primary">
                      <input type="checkbox" checked={(filters.sources || []).includes(src.key)}
                        onChange={() => handleSourceToggle(src.key)}
                        className="rounded text-brand-500 focus:ring-brand-500/30 shrink-0" />
                      <span className="flex-1 truncate">{src.label}</span>
                      <span className="text-xs t-faint">{src.count}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            <div>
              <p className="text-xs font-medium t-faint uppercase tracking-wider mb-2">Min. Match Score</p>
              <input type="range" min="0" max="100" step="10" value={filters.minScore || 0}
                onChange={(e) => onFilterChange({ ...filters, minScore: parseInt(e.target.value) })}
                className="w-full accent-brand-500" />
              <div className="flex justify-between text-xs t-faint mt-1">
                <span>0%</span>
                <span className="font-medium text-brand-500">{filters.minScore || 0}%+</span>
                <span>100%</span>
              </div>
            </div>

            <div>
              <p className="text-xs font-medium t-faint uppercase tracking-wider mb-2">Posted Within</p>
              <div className="space-y-1">
                {DATE_OPTIONS.map((opt) => (
                  <label key={opt.value} className="flex items-center gap-2 cursor-pointer text-sm t-muted hover:t-primary">
                    <input type="radio" name="dateFilter" checked={(filters.days || 0) === opt.value}
                      onChange={() => onFilterChange({ ...filters, days: opt.value })}
                      className="border-gray-400 dark:border-surface-600 text-brand-500 focus:ring-brand-500/30" />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>

            {onToggleDismissed && (
              <div className="pt-3 border-t border-themed">
                <button
                  onClick={onToggleDismissed}
                  className="flex items-center justify-between w-full text-sm t-muted hover:t-primary"
                >
                  <div className="flex items-center gap-2">
                    {showDismissed ? <Eye className="w-4 h-4 text-brand-500" /> : <EyeOff className="w-4 h-4 t-faint" />}
                    <span>{showDismissed ? 'Hide dismissed' : 'Show dismissed'}</span>
                  </div>
                  {dismissedCount > 0 && (
                    <span className="badge bg-themed-elevated t-muted border border-themed">{dismissedCount}</span>
                  )}
                </button>
              </div>
            )}

            <div className="pt-3 border-t border-themed">
              <button onClick={onManageBlacklist} className="flex items-center justify-between w-full text-sm t-muted hover:t-primary">
                <div className="flex items-center gap-2">
                  <Ban className="w-4 h-4 text-red-500" /> <span>Blacklist</span>
                </div>
                {blacklistCount > 0 && (
                  <span className="badge bg-red-500/15 text-red-500 border border-red-500/25">{blacklistCount}</span>
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
