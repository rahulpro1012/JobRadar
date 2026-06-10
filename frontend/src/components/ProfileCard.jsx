import { User, MapPin, Briefcase, GraduationCap, Pencil, Sparkles, Ban } from 'lucide-react';

export default function ProfileCard({ profile, onClick }) {
  if (!profile) return null;

  const core = profile.core_skills || [];
  const secondary = profile.secondary_skills || [];
  const tools = profile.tools || [];

  // A1: tiered profile (schema v2)
  const tiered = profile.skills_tiered && typeof profile.skills_tiered === 'object' ? profile.skills_tiered : null;
  const prefs = profile.preferences_explicit && typeof profile.preferences_explicit === 'object'
    ? profile.preferences_explicit : {};
  const dealBreakers = Array.isArray(profile.deal_breakers) ? profile.deal_breakers : [];
  const preferredLocations = Array.isArray(prefs.preferred_locations) ? prefs.preferred_locations : [];
  const isV2 = (profile.schema_version || 1) >= 2 && tiered &&
    ((tiered.primary?.length || 0) + (tiered.familiar?.length || 0) + (tiered.learning?.length || 0) > 0);

  const skillName = (s) => (typeof s === 'string' ? s : s?.name || '');
  const skillLabel = (s) => {
    if (typeof s === 'string') return s;
    const yrs = s?.years;
    return yrs ? `${s.name} · ${yrs}y` : (s?.name || '');
  };

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
          {isV2 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium
                             bg-violet-500/10 text-violet-600 dark:text-violet-400 border border-violet-500/20">
              <Sparkles className="w-3 h-3" /> AI-tiered
            </span>
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

      {isV2 ? (
        <div className="space-y-2">
          {tiered.primary?.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-semibold t-faint uppercase tracking-wide mr-1">Primary</span>
              {tiered.primary.slice(0, 8).map((s) => (
                <span key={skillName(s)} className="skill-tag">{skillLabel(s)}</span>
              ))}
            </div>
          )}
          {tiered.familiar?.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-semibold t-faint uppercase tracking-wide mr-1">Familiar</span>
              {tiered.familiar.slice(0, 6).map((s) => (
                <span key={skillName(s)} className="skill-tag-secondary">{skillLabel(s)}</span>
              ))}
            </div>
          )}
          {tiered.learning?.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-semibold t-faint uppercase tracking-wide mr-1">Learning</span>
              {tiered.learning.slice(0, 6).map((s) => (
                <span key={skillName(s)} className="skill-tag-tool">{skillName(s)}</span>
              ))}
            </div>
          )}
          {(dealBreakers.length > 0 || preferredLocations.length > 0) && (
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              {preferredLocations.slice(0, 4).map((l) => (
                <span key={l} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs
                                         bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                  <MapPin className="w-3 h-3" />{l}
                </span>
              ))}
              {dealBreakers.slice(0, 4).map((d) => (
                <span key={d} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs
                                         bg-red-500/10 text-red-500 border border-red-500/20">
                  <Ban className="w-3 h-3" />{d}
                </span>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {core.slice(0, 8).map((s) => (<span key={s} className="skill-tag">{s}</span>))}
          {secondary.slice(0, 4).map((s) => (<span key={s} className="skill-tag-secondary">{s}</span>))}
          {tools.slice(0, 3).map((s) => (<span key={s} className="skill-tag-tool">{s}</span>))}
          {core.length + secondary.length + tools.length > 15 && (
            <span className="skill-tag-secondary">+{core.length + secondary.length + tools.length - 15} more</span>
          )}
        </div>
      )}
    </div>
  );
}
