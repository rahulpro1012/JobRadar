import { Briefcase, Star, Bookmark, CheckCircle2, TrendingUp } from 'lucide-react';

export default function StatsBar({ stats }) {
  if (!stats) return null;

  const items = [
    {
      icon: Briefcase,
      label: "Total Jobs",
      value: stats.total || 0,
      iconColor: "text-brand-500",
      borderColor: "border-brand-500/30",
      bgClass: "bg-brand-500/5",
    },
    {
      icon: Star,
      label: "Excellent",
      value: stats.by_score?.excellent || 0,
      iconColor: "text-emerald-500",
      borderColor: "border-emerald-500/30",
      bgClass: "bg-emerald-500/5",
    },
    {
      icon: TrendingUp,
      label: "Good Match",
      value: stats.by_score?.good || 0,
      iconColor: "text-blue-500",
      borderColor: "border-blue-500/15",
      bgClass: "bg-blue-500/5",
    },
    {
      icon: Bookmark,
      label: "Saved",
      value: stats.by_status?.saved || 0,
      iconColor: "text-amber-500",
      borderColor: "border-amber-500/30",
      bgClass: "bg-amber-500/5",
    },
    {
      icon: CheckCircle2,
      label: "Applied",
      value: stats.by_status?.applied || 0,
      iconColor: "text-violet-500",
      borderColor: "border-violet-500/15",
      bgClass: "bg-violet-500/5",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
      {items.map((item) => (
        <div
          key={item.label}
          className={`rounded-xl border ${item.borderColor} ${item.bgClass} px-4 py-3 flex items-center gap-3 transition-all duration-200 hover:scale-[1.02]`}
        >
          <item.icon className={`w-5 h-5 ${item.iconColor}`} />
          <div>
            <p className="text-xl font-bold t-primary">{item.value}</p>
            <p className="text-xs t-muted">{item.label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
