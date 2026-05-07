import { User, MapPin, Briefcase, GraduationCap, Pencil } from 'lucide-react';

export default function ProfileCard({ profile, onClick }) {
  if (!profile) return null;

  const core = profile.core_skills || [];
  const secondary = profile.secondary_skills || [];
  const tools = profile.tools || [];

  return (
    <div
      onClick={onClick}
      className="card px-5 py-4 mb-5 cursor-pointer group hover:border-brand-500/30 transition-all duration-200"
      title="Click to view and edit your profile"
    >
      <div className="flex items-start justify-between">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-3 flex-1">
          {profile.name && (
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-brand-500" />
              <span className="font-semibold t-primary">{profile.name}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <Briefcase className="w-4 h-4 text-brand-500" />
            <span className="text-sm font-medium text-brand-600 dark:text-brand-400">{profile.primary_role}</span>
          </div>
          <span className="text-sm t-muted">{profile.experience_years}yr · {profile.experience_level}</span>
          <div className="flex items-center gap-1.5">
            <MapPin className="w-3.5 h-3.5 t-faint" />
            <span className="text-sm t-muted">{profile.location || 'No location'}</span>
          </div>
          {profile.education && (
            <div className="flex items-center gap-1.5">
              <GraduationCap className="w-3.5 h-3.5 t-faint" />
              <span className="text-sm t-muted">{profile.education}</span>
            </div>
          )}
        </div>
        {/* Edit hint */}
        <div className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium
                           bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20">
            <Pencil className="w-3 h-3" /> Edit
          </span>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {core.slice(0, 8).map((s) => (<span key={s} className="skill-tag">{s}</span>))}
        {secondary.slice(0, 4).map((s) => (<span key={s} className="skill-tag-secondary">{s}</span>))}
        {tools.slice(0, 3).map((s) => (<span key={s} className="skill-tag-tool">{s}</span>))}
        {core.length + secondary.length + tools.length > 15 && (
          <span className="skill-tag-secondary">+{core.length + secondary.length + tools.length - 15} more</span>
        )}
      </div>
    </div>
  );
}
