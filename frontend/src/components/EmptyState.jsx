import { Upload, Search, Radar } from 'lucide-react';

export default function EmptyState({ type, onAction }) {
  const states = {
    noProfile: {
      icon: Upload,
      title: 'Upload your resume to get started',
      description:
        'JobRadar will parse your skills and experience, then find matching jobs across Naukri, LinkedIn, Indeed, and company career pages.',
      actionLabel: 'Upload Resume',
    },
    noJobs: {
      icon: Search,
      title: 'No jobs found yet',
      description:
        'Click Refresh to search for matching jobs based on your resume profile. New jobs from multiple sources will appear here.',
      actionLabel: 'Refresh Jobs',
    },
    noResults: {
      icon: Radar,
      title: 'No jobs match current filters',
      description:
        'Try adjusting the filters in the sidebar, or lower the minimum match score to see more results.',
      actionLabel: null,
    },
  };

  const s = states[type] || states.noJobs;

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="w-16 h-16 rounded-2xl bg-brand-50 flex items-center justify-center mb-5">
        <s.icon className="w-8 h-8 text-brand-500" />
      </div>
      <h3 className="font-display font-semibold text-lg text-surface-800 mb-2 text-center">
        {s.title}
      </h3>
      <p className="text-sm text-surface-500 text-center max-w-md mb-6">
        {s.description}
      </p>
      {s.actionLabel && onAction && (
        <button onClick={onAction} className="btn-primary">
          {s.actionLabel}
        </button>
      )}
    </div>
  );
}
