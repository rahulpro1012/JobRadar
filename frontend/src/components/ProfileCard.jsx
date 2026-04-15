import { User, MapPin, Briefcase, GraduationCap, Pencil } from 'lucide-react';
import { useState } from 'react';
import { updateProfile } from '../services/api';

export default function ProfileCard({ profile, onProfileUpdate }) {
  const [editing, setEditing] = useState(false);
  const [editLocation, setEditLocation] = useState(profile?.location || '');

  if (!profile) return null;

  const core = profile.core_skills || [];
  const secondary = profile.secondary_skills || [];
  const tools = profile.tools || [];

  const handleSaveLocation = async () => {
    try {
      const res = await updateProfile({ location: editLocation });
      if (onProfileUpdate) onProfileUpdate(res.data.profile);
      setEditing(false);
    } catch {
      // Silently fail
    }
  };

  return (
    <div className="card px-5 py-4 mb-5">
      {/* Top row: Name + Role + Experience */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-3">
        {profile.name && (
          <div className="flex items-center gap-2">
            <User className="w-4 h-4 text-surface-400" />
            <span className="font-semibold text-surface-800">{profile.name}</span>
          </div>
        )}
        <div className="flex items-center gap-2">
          <Briefcase className="w-4 h-4 text-brand-500" />
          <span className="text-sm font-medium text-brand-700">{profile.primary_role}</span>
        </div>
        <span className="text-sm text-surface-500">
          {profile.experience_years}yr exp · {profile.experience_level}
        </span>
        {/* Location with inline edit */}
        <div className="flex items-center gap-1.5">
          <MapPin className="w-3.5 h-3.5 text-surface-400" />
          {editing ? (
            <div className="flex items-center gap-1">
              <input
                className="input py-0.5 px-2 text-sm w-28"
                value={editLocation}
                onChange={(e) => setEditLocation(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSaveLocation()}
                autoFocus
              />
              <button onClick={handleSaveLocation} className="text-xs text-brand-600 font-medium">
                Save
              </button>
              <button onClick={() => setEditing(false)} className="text-xs text-surface-400">
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => { setEditLocation(profile.location || ''); setEditing(true); }}
              className="flex items-center gap-1 text-sm text-surface-600 hover:text-brand-600 transition-colors"
            >
              {profile.location || 'Set location'}
              <Pencil className="w-3 h-3 opacity-0 group-hover:opacity-100" />
            </button>
          )}
        </div>
        {profile.education && (
          <div className="flex items-center gap-1.5">
            <GraduationCap className="w-3.5 h-3.5 text-surface-400" />
            <span className="text-sm text-surface-500">{profile.education}</span>
          </div>
        )}
      </div>

      {/* Skills row */}
      <div className="flex flex-wrap gap-1.5">
        {core.slice(0, 8).map((s) => (
          <span key={s} className="px-2 py-0.5 text-xs rounded-md bg-brand-50 text-brand-700 font-medium">
            {s}
          </span>
        ))}
        {secondary.slice(0, 4).map((s) => (
          <span key={s} className="px-2 py-0.5 text-xs rounded-md bg-surface-100 text-surface-600">
            {s}
          </span>
        ))}
        {tools.slice(0, 3).map((s) => (
          <span key={s} className="px-2 py-0.5 text-xs rounded-md bg-amber-50 text-amber-700">
            {s}
          </span>
        ))}
        {core.length + secondary.length + tools.length > 15 && (
          <span className="px-2 py-0.5 text-xs rounded-md bg-surface-100 text-surface-400">
            +{core.length + secondary.length + tools.length - 15} more
          </span>
        )}
      </div>
    </div>
  );
}
