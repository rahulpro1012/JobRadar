import {
  ExternalLink, Bookmark, BookmarkCheck, SkipForward,
  CheckCircle2, MoreHorizontal, Ban, MapPin, Clock, Building2,
} from 'lucide-react';
import { useState } from 'react';
import { getScoreBadge, timeAgo, sourceName, sourceColor } from '../utils/helpers';

export default function JobCard({ job, onStatusChange, onBlockSource, onBlockCompany }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [imgError, setImgError] = useState(false);
  const score = job.adjusted_score || job.match_score || 0;
  const badge = getScoreBadge(score);
  const skills = job.skills_found || [];
  const alsoOn = job.also_on || [];

  // Company logo URL (Clearbit free API)
  const companyDomain = job.source_domain || '';
  const logoUrl = companyDomain && !imgError
    ? `https://logo.clearbit.com/${companyDomain}`
    : null;

  const statusIcons = {
    applied: <CheckCircle2 className="w-3.5 h-3.5" />,
    saved: <BookmarkCheck className="w-3.5 h-3.5" />,
    skipped: <SkipForward className="w-3.5 h-3.5" />,
  };

  return (
    <div className="card p-4 relative group animate-fade-in">
      <div className="flex gap-3">
        {/* Company logo */}
        <div className="hidden sm:flex shrink-0 w-11 h-11 rounded-lg bg-surface-800 border border-surface-700 items-center justify-center overflow-hidden">
          {logoUrl ? (
            <img
              src={logoUrl}
              alt=""
              className="w-7 h-7 object-contain"
              onError={() => setImgError(true)}
            />
          ) : (
            <Building2 className="w-5 h-5 text-surface-600" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Title + Score */}
          <div className="flex items-start justify-between gap-3 mb-1">
            <h3 className="font-semibold text-surface-100 leading-snug line-clamp-2">
              {job.title}
            </h3>
            <span className={`badge shrink-0 ${badge.cls}`}>
              {score}%
            </span>
          </div>

          {/* Company + Location */}
          <div className="flex items-center gap-3 text-sm text-surface-400 mb-2.5">
            <span className="font-medium text-surface-300">{job.company}</span>
            {job.location && (
              <span className="flex items-center gap-1">
                <MapPin className="w-3 h-3" />
                {job.location}
              </span>
            )}
          </div>

          {/* Skills tags */}
          {skills.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2.5">
              {skills.slice(0, 6).map((skill) => (
                <span key={skill} className="skill-tag">{skill}</span>
              ))}
              {skills.length > 6 && (
                <span className="skill-tag-secondary">+{skills.length - 6}</span>
              )}
            </div>
          )}

          {/* Description snippet */}
          {job.description_snippet && (
            <p className="text-sm text-surface-500 line-clamp-2 mb-2.5">
              {job.description_snippet}
            </p>
          )}

          {/* AI Insight */}
          {job.ai_reason && (
            <div className="flex items-start gap-2 mb-3 px-3 py-2 rounded-lg bg-accent-500/10 border border-accent-500/20">
              <span className="text-sm mt-0.5">🤖</span>
              <div>
                <span className="text-xs font-semibold text-accent-400">AI Analysis</span>
                <p className="text-xs text-accent-300/80 leading-relaxed">{job.ai_reason}</p>
              </div>
            </div>
          )}

          {/* Source + Posted date */}
          <div className="flex items-center gap-2 mb-3">
            <span className={`badge text-xs ${sourceColor(job.source_domain)}`}>
              {sourceName(job.source_domain)}
            </span>
            {alsoOn.length > 0 && (
              <span className="text-xs text-surface-500">
                also on: {alsoOn.map(a => sourceName(typeof a === 'string' ? a : a.source || '')).join(', ')}
              </span>
            )}
            {job.posted_date && (
              <span className="flex items-center gap-1 text-xs text-surface-500 ml-auto">
                <Clock className="w-3 h-3" />
                {timeAgo(job.posted_date)}
              </span>
            )}
          </div>

          {/* Action row */}
          <div className="flex items-center gap-2 pt-2.5 border-t border-surface-800">
            <a
              href={job.source_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => onStatusChange(job.id, 'applied')}
              className="btn-primary text-xs py-1.5 px-3"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Apply
            </a>

            {job.status !== 'saved' ? (
              <button
                onClick={() => onStatusChange(job.id, 'saved')}
                className="btn-ghost text-xs"
              >
                <Bookmark className="w-3.5 h-3.5" />
                Save
              </button>
            ) : (
              <span className="btn-ghost text-xs text-brand-400">
                <BookmarkCheck className="w-3.5 h-3.5" />
                Saved
              </span>
            )}

            {job.status !== 'skipped' && (
              <button
                onClick={() => onStatusChange(job.id, 'skipped')}
                className="btn-ghost text-xs"
              >
                <SkipForward className="w-3.5 h-3.5" />
                Skip
              </button>
            )}

            {job.status && job.status !== 'new' && statusIcons[job.status] && (
              <span className="ml-auto badge bg-surface-800 text-surface-400 gap-1 border border-surface-700">
                {statusIcons[job.status]}
                {job.status}
              </span>
            )}

            <div className="relative ml-auto">
              <button
                onClick={() => setMenuOpen(!menuOpen)}
                className="btn-ghost text-xs p-1.5"
              >
                <MoreHorizontal className="w-4 h-4" />
              </button>
              {menuOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                  <div className="absolute right-0 bottom-full mb-1 z-20 bg-surface-800 rounded-lg shadow-xl border border-surface-700 py-1 w-48">
                    <button
                      onClick={() => { onBlockSource(job.source_domain); setMenuOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10"
                    >
                      <Ban className="w-3.5 h-3.5" />
                      Block {sourceName(job.source_domain)}
                    </button>
                    <button
                      onClick={() => { onBlockCompany(job.company); setMenuOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10"
                    >
                      <Ban className="w-3.5 h-3.5" />
                      Block {job.company}
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
