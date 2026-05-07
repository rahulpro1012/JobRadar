import { useState, useEffect } from "react";
import { RefreshCw } from "lucide-react";

export default function LastRefreshed({ timestamp, onRefresh, isRefreshing }) {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => forceUpdate((n) => n + 1), 60000);
    return () => clearInterval(timer);
  }, []);

  if (!timestamp) return null;

  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);

  let timeText;
  let dotColor;
  let pillBg;
  let pillBorder;
  let stale = false;

  if (minutes < 5) {
    timeText = "just now";
    dotColor = "bg-emerald-500";
    pillBg = "bg-emerald-500/10";
    pillBorder = "border-emerald-500/25";
  } else if (minutes < 15) {
    timeText = `${minutes}m ago`;
    dotColor = "bg-emerald-500";
    pillBg = "bg-emerald-500/10";
    pillBorder = "border-emerald-500/25";
    // Green but no pulse (handled below)
  } else if (minutes < 30) {
    timeText = `${minutes}m ago`;
    dotColor = "bg-amber-500";
    pillBg = "bg-amber-500/10";
    pillBorder = "border-amber-500/25";
    stale = true;
  } else if (hours < 1) {
    timeText = `${minutes}m ago`;
    dotColor = "bg-red-500";
    pillBg = "bg-red-500/10";
    pillBorder = "border-red-500/25";
    stale = true;
  } else if (hours < 24) {
    timeText = `${hours}h ago`;
    dotColor = "bg-red-500";
    pillBg = "bg-red-500/10";
    pillBorder = "border-red-500/25";
    stale = true;
  } else {
    timeText = `${Math.floor(hours / 24)}d ago`;
    dotColor = "bg-red-500";
    pillBg = "bg-red-500/10";
    pillBorder = "border-red-500/25";
    stale = true;
  }

  return (
    <div className="flex items-center justify-between mb-4">
      <div
        className={`inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full border ${pillBg} ${pillBorder}`}
      >
        {/* Animated pulse dot */}
        <span className="relative flex h-2.5 w-2.5">
          <span
            className={`absolute inline-flex h-full w-full rounded-full ${dotColor} opacity-75 ${
              minutes < 5 ? "animate-ping" : ""
            }`}
          />
          <span
            className={`relative inline-flex rounded-full h-2.5 w-2.5 ${dotColor}`}
          />
        </span>
        <span className="text-xs font-medium t-secondary">
          Refreshed {timeText}
        </span>
      </div>

      {stale && !isRefreshing && (
        <button
          onClick={onRefresh}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                     bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/25
                     hover:bg-brand-500/20 transition-all duration-200"
        >
          <RefreshCw className="w-3 h-3" />
          Refresh now
        </button>
      )}
    </div>
  );
}
