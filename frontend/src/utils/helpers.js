/**
 * JobRadar utility helpers.
 */

/** Get score badge class and label */
export function getScoreBadge(score) {
  if (score >= 80) return { cls: 'badge-excellent', label: 'Excellent Match' };
  if (score >= 60) return { cls: 'badge-good', label: 'Good Match' };
  if (score >= 40) return { cls: 'badge-partial', label: 'Partial Match' };
  return { cls: 'badge-low', label: 'Low Match' };
}

/** Format relative time (e.g., "2d ago", "5h ago") */
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

/** Extract domain from URL */
export function extractDomain(url) {
  try {
    return new URL(url).hostname.replace('www.', '');
  } catch {
    return url;
  }
}

/** Capitalize first letter */
export function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/** Source domain to friendly name */
export function sourceName(domain) {
  const map = {
    'naukri.com': 'Naukri',
    'linkedin.com': 'LinkedIn',
    'indeed.co.in': 'Indeed',
    'indeed.com': 'Indeed',
  };
  return map[domain] || capitalize(domain.split('.')[0]);
}

/** Source domain to color */
export function sourceColor(domain) {
  const map = {
    'naukri.com': 'bg-blue-100 text-blue-700',
    'linkedin.com': 'bg-sky-100 text-sky-700',
    'indeed.co.in': 'bg-purple-100 text-purple-700',
    'indeed.com': 'bg-purple-100 text-purple-700',
  };
  return map[domain] || 'bg-surface-100 text-surface-600';
}

/** Quota percentage */
export function quotaPercent(used, limit) {
  if (limit <= 0) return -1; // unlimited
  return Math.min(100, Math.round((used / limit) * 100));
}
