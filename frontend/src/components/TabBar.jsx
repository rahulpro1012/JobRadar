const TABS = [
  { key: 'new', label: 'New Jobs' },
  { key: 'saved', label: 'Saved' },
  { key: 'applied', label: 'Applied' },
  { key: 'all', label: 'All' },
];

export default function TabBar({ activeTab, onTabChange, counts }) {
  return (
    <div className="flex items-center gap-1 border-b border-themed">
      {TABS.map((tab) => {
        const isActive = activeTab === tab.key;
        const count = tab.key === 'all' ? (counts?.total || 0) : (counts?.by_status?.[tab.key] || 0);
        return (
          <button key={tab.key} onClick={() => onTabChange(tab.key)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-all duration-200 ${
              isActive ? 'border-brand-500 text-brand-600 dark:text-brand-400'
                       : 'border-transparent t-muted hover:t-primary hover:border-gray-300 dark:hover:border-surface-600'
            }`}>
            {tab.label}
            {count > 0 && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                isActive ? 'bg-brand-500/20 text-brand-600 dark:text-brand-400'
                         : 'bg-themed-elevated t-faint'
              }`}>{count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
