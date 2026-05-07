import { Filter, Ban, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

const SOURCES = [
  { key: 'greenhouse.io', label: 'Greenhouse' },
  { key: 'lever.co', label: 'Lever' },
  { key: 'ashbyhq.com', label: 'Ashby' },
  { key: 'naukri.com', label: 'Naukri' },
  { key: 'linkedin.com', label: 'LinkedIn' },
  { key: 'indeed.co.in', label: 'Indeed' },
];

const DATE_OPTIONS = [
  { value: 1, label: 'Today' },
  { value: 3, label: 'Last 3 days' },
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 0, label: 'All time' },
];

export default function Sidebar({ filters, onFilterChange, blacklistCount, onManageBlacklist }) {
  const [showFilters, setShowFilters] = useState(true);

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
            <div>
              <p className="text-xs font-medium t-faint uppercase tracking-wider mb-2">Source</p>
              <div className="space-y-1.5">
                {SOURCES.map((src) => (
                  <label key={src.key} className="flex items-center gap-2 cursor-pointer text-sm t-muted hover:t-primary">
                    <input type="checkbox" checked={(filters.sources || []).includes(src.key)}
                      onChange={() => handleSourceToggle(src.key)}
                      className="rounded border-gray-400 dark:border-surface-600 text-brand-500 focus:ring-brand-500/30" />
                    {src.label}
                  </label>
                ))}
              </div>
            </div>

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
