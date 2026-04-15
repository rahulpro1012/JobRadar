import {
  ExternalLink,
  Bookmark,
  BookmarkCheck,
  SkipForward,
  CheckCircle2,
  MoreHorizontal,
  Ban,
  MapPin,
  Clock,
} from 'lucide-react';
import { useState } from 'react';
import { getScoreBadge, timeAgo, sourceName, sourceColor } from '../utils/helpers';

export default function JobCard({ job, onStatusChange, onBlockSource, onBlockCompany }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const score = job.adjusted_score || job.match_score || 0;
  const badge = getScoreBadge(score);
  const skills = job.skills_found || [];
  const alsoOn = job.also_on || [];

  const statusIcons = {
    applied: <CheckCircle2 className="w-3.5 h-3.5" />,
    saved: <BookmarkCheck className="w-3.5 h-3.5" />,
    skipped: <SkipForward className="w-3.5 h-3.5" />,
  };

  return (
    <div className="card p-4 relative group">
      {/* Top row: Title + Score */}
      <div className="flex items-start justify-between gap-3 mb-1.5">
        <h3 className="font-semibold text-surface-900 leading-snug line-clamp-2">
          {job.title}
        </h3>
        <span className={`badge shrink-0 ${badge.cls}`}>
          {score}%
        </span>
      </div>

      {/* Company + Location */}
      <div className="flex items-center gap-3 text-sm text-surface-500 mb-2.5">
        <span className="font-medium text-surface-700">{job.company}</span>
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
            <span
              key={skill}
              className="px-2 py-0.5 text-xs rounded-md bg-brand-50 text-brand-700 font-medium"
            >
              {skill}
            </span>
          ))}
          {skills.length > 6 && (
            <span className="px-2 py-0.5 text-xs rounded-md bg-surface-100 text-surface-500">
              +{skills.length - 6}
            </span>
          )}
        </div>
      )}

      {/* Description snippet */}
      {job.description_snippet && (
        <p className="text-sm text-surface-500 line-clamp-2 mb-3">
          {job.description_snippet}
        </p>
      )}

      {/* Source + Posted date */}
      <div className="flex items-center gap-2 mb-3">
        <span className={`badge text-xs ${sourceColor(job.source_domain)}`}>
          {sourceName(job.source_domain)}
        </span>
        {alsoOn.length > 0 && (
          <span className="text-xs text-surface-400">
            also on: {alsoOn.map(sourceName).join(', ')}
          </span>
        )}
        {job.posted_date && (
          <span className="flex items-center gap-1 text-xs text-surface-400 ml-auto">
            <Clock className="w-3 h-3" />
            {timeAgo(job.posted_date)}
          </span>
        )}
      </div>

      {/* Action row */}
      <div className="flex items-center gap-2 pt-2 border-t border-surface-100">
        {/* Apply button */}
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

        {/* Save */}
        {job.status !== 'saved' ? (
          <button
            onClick={() => onStatusChange(job.id, 'saved')}
            className="btn-ghost text-xs"
            title="Save for later"
          >
            <Bookmark className="w-3.5 h-3.5" />
            Save
          </button>
        ) : (
          <span className="btn-ghost text-xs text-brand-600">
            <BookmarkCheck className="w-3.5 h-3.5" />
            Saved
          </span>
        )}

        {/* Skip */}
        {job.status !== 'skipped' && (
          <button
            onClick={() => onStatusChange(job.id, 'skipped')}
            className="btn-ghost text-xs"
            title="Skip this job"
          >
            <SkipForward className="w-3.5 h-3.5" />
            Skip
          </button>
        )}

        {/* Status indicator */}
        {job.status && job.status !== 'new' && statusIcons[job.status] && (
          <span className="ml-auto badge bg-surface-100 text-surface-600 gap-1">
            {statusIcons[job.status]}
            {job.status}
          </span>
        )}

        {/* More menu */}
        <div className="relative ml-auto">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="btn-ghost text-xs p-1.5"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>
          {menuOpen && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setMenuOpen(false)}
              />
              <div className="absolute right-0 bottom-full mb-1 z-20 bg-white rounded-lg shadow-lg border border-surface-200 py-1 w-48">
                <button
                  onClick={() => {
                    onBlockSource(job.source_domain);
                    setMenuOpen(false);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  <Ban className="w-3.5 h-3.5" />
                  Block {sourceName(job.source_domain)}
                </button>
                <button
                  onClick={() => {
                    onBlockCompany(job.company);
                    setMenuOpen(false);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
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
  );
}
