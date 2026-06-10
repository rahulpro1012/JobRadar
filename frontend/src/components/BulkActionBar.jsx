import { X, Ban } from 'lucide-react';

export default function BulkActionBar({ selectedCount, onDismissAll, onClear }) {
  if (!selectedCount) return null;

  return (
    <div className="sticky top-16 z-20 mb-3 flex items-center gap-3 px-4 py-2.5 rounded-xl
                    bg-brand-500/10 border border-brand-500/25 backdrop-blur-sm">
      <span className="text-sm font-medium text-brand-600 dark:text-brand-400">
        {selectedCount} selected
      </span>
      <button onClick={onDismissAll} className="btn-danger text-xs py-1.5 px-3">
        <Ban className="w-3.5 h-3.5" /> Dismiss {selectedCount}
      </button>
      <button onClick={onClear} className="btn-ghost text-xs ml-auto">
        <X className="w-3.5 h-3.5" /> Clear
      </button>
    </div>
  );
}
