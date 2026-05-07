import { Briefcase, Star, Bookmark, CheckCircle2, TrendingUp } from 'lucide-react';

export default function StatsBar({ stats }) {
  if (!stats) return null;

  const items = [
    { icon: Briefcase, label: 'Total Jobs', value: stats.total || 0,
      gradient: 'from-surface-800 to-surface-850', iconColor: 'text-surface-400', border: 'border-surface-700' },
    { icon: Star, label: 'Excellent', value: stats.by_score?.excellent || 0,
      gradient: 'from-emerald-500/10 to-emerald-500/5', iconColor: 'text-emerald-400', border: 'border-emerald-500/20' },
    { icon: TrendingUp, label: 'Good Match', value: stats.by_score?.good || 0,
      gradient: 'from-brand-500/10 to-brand-500/5', iconColor: 'text-brand-400', border: 'border-brand-500/20' },
    { icon: Bookmark, label: 'Saved', value: stats.by_status?.saved || 0,
      gradient: 'from-amber-500/10 to-amber-500/5', iconColor: 'text-amber-400', border: 'border-amber-500/20' },
    { icon: CheckCircle2, label: 'Applied', value: stats.by_status?.applied || 0,
      gradient: 'from-accent-500/10 to-accent-500/5', iconColor: 'text-accent-400', border: 'border-accent-500/20' },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
      {items.map((item) => (
        <div
          key={item.label}
          className={`rounded-xl border ${item.border} bg-gradient-to-br ${item.gradient} px-4 py-3 flex items-center gap-3 transition-all duration-200 hover:scale-[1.02]`}
        >
          <item.icon className={`w-5 h-5 ${item.iconColor}`} />
          <div>
            <p className="text-xl font-bold text-surface-100">{item.value}</p>
            <p className="text-xs text-surface-500">{item.label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
