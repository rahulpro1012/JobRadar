import {
  ExternalLink, Bookmark, BookmarkCheck, SkipForward,
  CheckCircle2, MoreHorizontal, Ban, MapPin, Clock, Building2,
  X, Check, AlertTriangle, RotateCcw, ChevronDown, ChevronUp,
} from 'lucide-react';
import { useState } from 'react';
import { getScoreBadge, timeAgo, sourceName, sourceColor, redFlagLabel } from '../utils/helpers';

export default function JobCard({
  job, onStatusChange, onBlockSource, onBlockCompany,
  onDismiss, onUndismiss, selected = false, onToggleSelect,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [reasonsExpanded, setReasonsExpanded] = useState(false);
  const score = job.adjusted_score || job.match_score || 0;
  const badge = getScoreBadge(score);
  const skills = job.skills_found || [];
  const alsoOn = job.also_on || [];
  const isDismissed = !!job.dismissed_at;

  // C1 structured analysis (arrives via LEFT JOIN job_ai_analysis)
  const applyReasons = Array.isArray(job.apply_reasons) ? job.apply_reasons : [];
  const skipReasons = Array.isArray(job.skip_reasons) ? job.skip_reasons : [];
  const redFlags = Array.isArray(job.red_flags) ? job.red_flags : [];
  const fitSummary = job.ai_fit_summary || job.ai_reason || '';
  const hasC1 = applyReasons.length > 0 || skipReasons.length > 0 || redFlags.length > 0 || !!job.ai_fit_summary;
  const reasonLimit = reasonsExpanded ? 99 : 2;
  const hiddenReasons =
    Math.max(0, applyReasons.length - reasonLimit) + Math.max(0, skipReasons.length - reasonLimit);

  const companyDomain = job.source_domain || '';
  const logoUrl = companyDomain && !imgError
    ? `https://logo.clearbit.com/${companyDomain}` : null;

  const statusIcons = {
    applied: <CheckCircle2 className="w-3.5 h-3.5" />,
    saved: <BookmarkCheck className="w-3.5 h-3.5" />,
    skipped: <SkipForward className="w-3.5 h-3.5" />,
  };

  return (
    <div className={`card p-4 relative group animate-fade-in ${isDismissed ? 'opacity-60' : ''}`}>
      <div className="flex gap-3">
        {/* Multi-select checkbox */}
        {onToggleSelect && (
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(job.id)}
            aria-label={`Select ${job.title}`}
            className="mt-1 shrink-0 w-4 h-4 accent-brand-600 cursor-pointer"
          />
        )}

        {/* Company logo */}
        <div className="hidden sm:flex shrink-0 w-11 h-11 rounded-lg bg-themed-elevated border border-themed items-center justify-center overflow-hidden">
          {logoUrl ? (
            <img src={logoUrl} alt="" className="w-7 h-7 object-contain" onError={() => setImgError(true)} />
          ) : (
            <Building2 className="w-5 h-5 t-faint" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          {/* Title + Score */}
          <div className="flex items-start justify-between gap-3 mb-1">
            <h3 className="font-semibold t-primary leading-snug line-clamp-2">{job.title}</h3>
            <div className="flex items-center gap-2 shrink-0">
              {isDismissed ? (
                <button
                  onClick={() => onUndismiss?.(job.id)}
                  className="btn-ghost text-xs px-2 py-1"
                  title="Restore job"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> Restore
                </button>
              ) : (
                onDismiss && (
                  <button
                    onClick={() => onDismiss(job)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity t-faint hover:text-red-500 p-1 rounded-md"
                    title="Dismiss job"
                    aria-label="Dismiss job"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )
              )}
              <span className={`badge ${badge.cls}`}>{score}%</span>
            </div>
          </div>

          {/* Company + Location */}
          <div className="flex items-center gap-3 text-sm t-muted mb-2.5">
            <span className="font-medium t-secondary">{job.company}</span>
            {job.location && (
              <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{job.location}</span>
            )}
          </div>

          {/* Skills */}
          {skills.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2.5">
              {skills.slice(0, 6).map((skill) => (<span key={skill} className="skill-tag">{skill}</span>))}
              {skills.length > 6 && (<span className="skill-tag-secondary">+{skills.length - 6}</span>)}
            </div>
          )}

          {/* Description */}
          {job.description_snippet && (
            <p className="text-sm t-muted line-clamp-2 mb-2.5">{job.description_snippet}</p>
          )}

          {/* AI Analysis (C1: structured reasoning) */}
          {hasC1 ? (
            <div className="mb-3 px-3 py-2.5 rounded-lg bg-violet-500/10 border border-violet-500/20 space-y-2">
              <div className="flex items-start gap-2">
                <span className="text-sm">🤖</span>
                <div className="min-w-0">
                  <span className="text-xs font-semibold text-violet-600 dark:text-violet-400">AI Analysis</span>
                  {fitSummary && (
                    <p className="text-xs text-violet-600/80 dark:text-violet-300/80 leading-relaxed">{fitSummary}</p>
                  )}
                </div>
              </div>

              {/* Apply reasons */}
              {applyReasons.slice(0, reasonLimit).map((r, i) => (
                <div key={`a-${i}`} className="flex items-start gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
                  <Check className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span className="leading-relaxed">{r}</span>
                </div>
              ))}

              {/* Skip reasons */}
              {skipReasons.slice(0, reasonLimit).map((r, i) => (
                <div key={`s-${i}`} className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span className="leading-relaxed">{r}</span>
                </div>
              ))}

              {/* Show more / less */}
              {(hiddenReasons > 0 || reasonsExpanded) && (applyReasons.length + skipReasons.length) > 4 && (
                <button
                  onClick={() => setReasonsExpanded(!reasonsExpanded)}
                  className="flex items-center gap-1 text-xs t-muted hover:t-primary"
                >
                  {reasonsExpanded
                    ? (<><ChevronUp className="w-3 h-3" /> Show less</>)
                    : (<><ChevronDown className="w-3 h-3" /> Show {hiddenReasons} more</>)}
                </button>
              )}

              {/* Red flags */}
              {redFlags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                  {redFlags.map((flag) => (
                    <span key={flag} className="badge bg-red-500/15 text-red-500 border border-red-500/25 gap-1">
                      <AlertTriangle className="w-3 h-3" /> {redFlagLabel(flag)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            job.ai_reason && (
              <div className="flex items-start gap-2 mb-3 px-3 py-2 rounded-lg bg-violet-500/10 border border-violet-500/20">
                <span className="text-sm mt-0.5">🤖</span>
                <div>
                  <span className="text-xs font-semibold text-violet-600 dark:text-violet-400">AI Analysis</span>
                  <p className="text-xs text-violet-600/80 dark:text-violet-300/80 leading-relaxed">{job.ai_reason}</p>
                </div>
              </div>
            )
          )}

          {/* Source + Date */}
          <div className="flex items-center gap-2 mb-3">
            <span className={`badge text-xs ${sourceColor(job.source_domain)}`}>{sourceName(job.source_domain)}</span>
            {alsoOn.length > 0 && (
              <span className="text-xs t-faint">
                also on: {alsoOn.map(a => sourceName(typeof a === 'string' ? a : a.source || '')).join(', ')}
              </span>
            )}
            {job.posted_date && (
              <span className="flex items-center gap-1 text-xs t-faint ml-auto">
                <Clock className="w-3 h-3" />{timeAgo(job.posted_date)}
              </span>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2.5 border-t border-themed">
            <a href={job.source_url} target="_blank" rel="noopener noreferrer"
              onClick={() => onStatusChange(job.id, 'applied')} className="btn-primary text-xs py-1.5 px-3">
              <ExternalLink className="w-3.5 h-3.5" /> Apply
            </a>

            {job.status !== 'saved' ? (
              <button onClick={() => onStatusChange(job.id, 'saved')} className="btn-ghost text-xs">
                <Bookmark className="w-3.5 h-3.5" /> Save
              </button>
            ) : (
              <span className="btn-ghost text-xs text-brand-500"><BookmarkCheck className="w-3.5 h-3.5" /> Saved</span>
            )}

            {job.status !== 'skipped' && (
              <button onClick={() => onStatusChange(job.id, 'skipped')} className="btn-ghost text-xs">
                <SkipForward className="w-3.5 h-3.5" /> Skip
              </button>
            )}

            {job.status && job.status !== 'new' && statusIcons[job.status] && (
              <span className="ml-auto badge bg-themed-elevated t-muted gap-1 border border-themed">
                {statusIcons[job.status]} {job.status}
              </span>
            )}

            <div className="relative ml-auto">
              <button onClick={() => setMenuOpen(!menuOpen)} className="btn-ghost text-xs p-1.5">
                <MoreHorizontal className="w-4 h-4" />
              </button>
              {menuOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                  <div className="absolute right-0 bottom-full mb-1 z-20 bg-themed-card rounded-lg shadow-xl border border-themed py-1 w-48">
                    <button onClick={() => { onBlockSource(job.source_domain); setMenuOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-500 hover:bg-red-500/10">
                      <Ban className="w-3.5 h-3.5" /> Block {sourceName(job.source_domain)}
                    </button>
                    <button onClick={() => { onBlockCompany(job.company); setMenuOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-500 hover:bg-red-500/10">
                      <Ban className="w-3.5 h-3.5" /> Block {job.company}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
