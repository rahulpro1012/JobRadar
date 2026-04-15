import { Briefcase, Star, Bookmark, CheckCircle2, TrendingUp } from 'lucide-react';

export default function StatsBar({ stats }) {
  if (!stats) return null;

  const items = [
    { icon: Briefcase, label: 'Total', value: stats.total || 0, color: 'text-surface-600' },
    { icon: Star, label: 'Excellent', value: stats.by_score?.excellent || 0, color: 'text-emerald-600' },
    { icon: TrendingUp, label: 'Good', value: stats.by_score?.good || 0, color: 'text-blue-600' },
    { icon: Bookmark, label: 'Saved', value: stats.by_status?.saved || 0, color: 'text-amber-600' },
    { icon: CheckCircle2, label: 'Applied', value: stats.by_status?.applied || 0, color: 'text-brand-600' },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="card px-4 py-3 flex items-center gap-3"
        >
          <item.icon className={`w-5 h-5 ${item.color}`} />
          <div>
            <p className="text-lg font-bold text-surface-900">{item.value}</p>
            <p className="text-xs text-surface-500">{item.label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
