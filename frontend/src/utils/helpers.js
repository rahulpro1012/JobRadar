/**
 * JobRadar utility helpers — Obsidian dark theme.
 */

export function getScoreBadge(score) {
  if (score >= 80) return { cls: 'badge-excellent', label: 'Excellent Match' };
  if (score >= 60) return { cls: 'badge-good', label: 'Good Match' };
  if (score >= 40) return { cls: 'badge-partial', label: 'Partial Match' };
  return { cls: 'badge-low', label: 'Low Match' };
}

export function timeAgo(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 30) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}

export function extractDomain(url) {
  try { return new URL(url).hostname.replace('www.', ''); }
  catch { return url; }
}

export function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

export function sourceName(domain) {
  if (!domain || typeof domain !== 'string') return 'Unknown';
  const map = {
    'naukri.com': 'Naukri',
    'linkedin.com': 'LinkedIn',
    'indeed.co.in': 'Indeed',
    'indeed.com': 'Indeed',
    'greenhouse.io': 'Greenhouse',
    'lever.co': 'Lever',
    'ashbyhq.com': 'Ashby',
    'jooble.org': 'Jooble',
    'google.com': 'Google Jobs',
  };
  return map[domain] || capitalize(domain.split('.')[0]);
}

export function sourceColor(domain) {
  if (!domain || typeof domain !== "string")
    return "border-themed t-muted border border-surface-700";
  const map = {
    "naukri.com": "bg-blue-500/15 text-blue-400 border border-blue-500/25",
    "linkedin.com": "bg-sky-500/15 text-sky-400 border border-sky-500/25",
    "indeed.co.in":
      "bg-purple-500/15 text-purple-400 border border-purple-500/25",
    "indeed.com":
      "bg-purple-500/15 text-purple-400 border border-purple-500/25",
    "greenhouse.io":
      "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25",
    "lever.co": "bg-orange-500/15 text-orange-400 border border-orange-500/25",
    "ashbyhq.com": "bg-pink-500/15 text-pink-400 border border-pink-500/25",
    "jooble.org": "bg-cyan-500/15 text-cyan-400 border border-cyan-500/25",
    "google.com":
      "bg-yellow-500/15 text-yellow-400 border border-yellow-500/25",
  };
  return map[domain] || "border-themed t-muted border border-surface-700";
}

export function quotaPercent(used, limit) {
  if (limit <= 0) return -1;
  return Math.min(100, Math.round((used / limit) * 100));
}

// C1: humanize red-flag tags from job_ai_analysis
const RED_FLAG_LABELS = {
  seniority_mismatch: 'Seniority mismatch',
  stale_posting: 'Stale posting',
  underpaid: 'Underpaid',
  generic_jd: 'Generic JD',
  experience_too_high: 'Over-qualified',
  location_mismatch: 'Location mismatch',
  stack_mismatch: 'Stack mismatch',
  body_shop: 'Body shop',
};

export function redFlagLabel(flag) {
  if (!flag || typeof flag !== 'string') return '';
  return RED_FLAG_LABELS[flag] || capitalize(flag.replace(/_/g, ' '));
}

// Source-health status → badge classes
export function sourceHealthColor(status) {
  const map = {
    healthy: 'bg-emerald-500/15 text-emerald-500 border border-emerald-500/25',
    degraded: 'bg-amber-500/15 text-amber-500 border border-amber-500/25',
    circuit_open: 'bg-red-500/15 text-red-500 border border-red-500/25',
  };
  return map[status] || 'bg-themed-elevated t-muted border border-themed';
}
