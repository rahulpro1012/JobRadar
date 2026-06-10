import { useState, useEffect } from 'react';
import { X, Save, Cpu, FileText, ChevronDown, ChevronUp, MapPin, Sparkles, Loader2, Ban } from 'lucide-react';
import TagInput from './TagInput';
import { updateProfile, reparseProfile } from '../services/api';
import { toast } from './Toast';

const EXPERIENCE_LEVELS = ['Junior', 'Junior-Mid', 'Mid', 'Senior', 'Lead/Principal'];

export default function ProfileEditor({ isOpen, onClose, profile, onProfileUpdate }) {
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [reparsing, setReparsing] = useState(false);
  const [showRawText, setShowRawText] = useState(false);

  useEffect(() => {
    if (isOpen && profile) {
      setForm({
        name: profile.name || '',
        primary_role: profile.primary_role || '',
        experience_years: profile.experience_years || 0,
        experience_level: profile.experience_level || '',
        location: profile.location || '',
        education: profile.education || '',
        core_skills: Array.isArray(profile.core_skills) ? [...profile.core_skills] : [],
        secondary_skills: Array.isArray(profile.secondary_skills) ? [...profile.secondary_skills] : [],
        tools: Array.isArray(profile.tools) ? [...profile.tools] : [],
        role_variants: Array.isArray(profile.role_variants) ? [...profile.role_variants] : [],
        domain_keywords: Array.isArray(profile.domain_keywords) ? [...profile.domain_keywords] : [],
        search_locations: Array.isArray(profile.search_locations) ? [...profile.search_locations] : [],
      });
    }
  }, [isOpen, profile]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await updateProfile(form);
      onProfileUpdate(res.data.profile);
      toast.success('Profile updated successfully');
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleReparse = async () => {
    setReparsing(true);
    try {
      const res = await reparseProfile();
      onProfileUpdate(res.data.profile);
      toast.success('Resume re-analyzed with tiered AI parsing (v2)');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Re-analysis failed');
    } finally {
      setReparsing(false);
    }
  };

  if (!isOpen || !profile) return null;

  const parseMethod = profile.resume_text ? 'Parsed from resume' : 'Manual';

  // A1: v2 tiered data (read-only display)
  const isV2 = (profile.schema_version || 1) >= 2;
  const tiered = profile.skills_tiered && typeof profile.skills_tiered === 'object' ? profile.skills_tiered : null;
  const prefs = profile.preferences_explicit && typeof profile.preferences_explicit === 'object'
    ? profile.preferences_explicit : {};
  const dealBreakers = Array.isArray(profile.deal_breakers) ? profile.deal_breakers : [];
  const skillRow = (s) => {
    if (typeof s === 'string') return { name: s, years: null, evidence: '' };
    return { name: s?.name || '', years: s?.years ?? null, evidence: s?.evidence || '' };
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-8 sm:pt-16 overflow-y-auto">
      <div className="fixed inset-0" style={{ backgroundColor: 'var(--overlay)' }} onClick={onClose} />

      <div className="relative w-full max-w-2xl rounded-2xl border border-themed shadow-2xl"
        style={{ backgroundColor: 'var(--bg-card)' }}>

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-themed">
          <div>
            <h2 className="font-display font-bold text-lg t-primary">Edit Profile</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <Cpu className="w-3.5 h-3.5 text-violet-500" />
              <span className="text-xs text-violet-600 dark:text-violet-400 font-medium">{parseMethod}</span>
              {isV2 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium
                                 bg-violet-500/10 text-violet-600 dark:text-violet-400 border border-violet-500/20">
                  <Sparkles className="w-3 h-3" /> AI-tiered (v2)
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {profile.resume_text && (
              <button
                onClick={handleReparse}
                disabled={reparsing}
                className="btn-secondary text-xs"
                title="Re-parse your resume into tiered skills + preferences"
              >
                {reparsing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                {reparsing ? 'Analyzing…' : 'Re-analyze with AI'}
              </button>
            )}
            <button onClick={onClose} className="btn-ghost p-1.5"><X className="w-5 h-5" /></button>
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-5 space-y-6 max-h-[70vh] overflow-y-auto">

          {/* A1: Tiered AI analysis (read-only) */}
          {isV2 && tiered && (
            <section className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-violet-500" />
                <h3 className="text-sm font-semibold t-secondary">AI Tiered Analysis</h3>
                <span className="text-xs t-faint">read-only · regenerate with “Re-analyze”</span>
              </div>

              {['primary', 'familiar', 'learning'].map((tier) => {
                const items = Array.isArray(tiered[tier]) ? tiered[tier] : [];
                if (items.length === 0) return null;
                return (
                  <div key={tier}>
                    <p className="text-xs font-semibold t-faint uppercase tracking-wide mb-1.5">{tier}</p>
                    <div className="space-y-1">
                      {items.map((s) => {
                        const row = skillRow(s);
                        return (
                          <div key={row.name} className="flex items-baseline gap-2 text-xs">
                            <span className="font-medium t-secondary">
                              {row.name}{row.years ? ` · ${row.years}y` : ''}
                            </span>
                            {row.evidence && <span className="t-faint truncate">— {row.evidence}</span>}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}

              {dealBreakers.length > 0 && (
                <div>
                  <p className="text-xs font-semibold t-faint uppercase tracking-wide mb-1.5">Deal-breakers</p>
                  <div className="flex flex-wrap gap-1.5">
                    {dealBreakers.map((d) => (
                      <span key={d} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs
                                               bg-red-500/10 text-red-500 border border-red-500/20">
                        <Ban className="w-3 h-3" />{d}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {(Array.isArray(prefs.preferred_locations) && prefs.preferred_locations.length > 0) && (
                <div>
                  <p className="text-xs font-semibold t-faint uppercase tracking-wide mb-1.5">Preferred locations</p>
                  <div className="flex flex-wrap gap-1.5">
                    {prefs.preferred_locations.map((l) => (
                      <span key={l} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs
                                               bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        <MapPin className="w-3 h-3" />{l}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {/* Basic Info */}
          <section>
            <h3 className="text-sm font-semibold t-secondary mb-3">Basic Information</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs t-muted mb-1 block">Full Name</label>
                <input className="input" value={form.name || ''}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div>
                <label className="text-xs t-muted mb-1 block">Primary Role</label>
                <input className="input" value={form.primary_role || ''}
                  onChange={(e) => setForm({ ...form, primary_role: e.target.value })} />
              </div>
              <div>
                <label className="text-xs t-muted mb-1 block">Experience (years)</label>
                <input className="input" type="number" step="0.5" min="0" max="30"
                  value={form.experience_years || 0}
                  onChange={(e) => setForm({ ...form, experience_years: parseFloat(e.target.value) || 0 })} />
              </div>
              <div>
                <label className="text-xs t-muted mb-1 block">Experience Level</label>
                <select className="input" value={form.experience_level || ''}
                  onChange={(e) => setForm({ ...form, experience_level: e.target.value })}>
                  <option value="">Select...</option>
                  {EXPERIENCE_LEVELS.map((l) => (<option key={l} value={l}>{l}</option>))}
                </select>
              </div>
              <div>
                <label className="text-xs t-muted mb-1 block">Primary Location</label>
                <input className="input" value={form.location || ''}
                  onChange={(e) => setForm({ ...form, location: e.target.value })}
                  placeholder="e.g., Pune" />
              </div>
              <div>
                <label className="text-xs t-muted mb-1 block">Education</label>
                <input className="input" value={form.education || ''}
                  onChange={(e) => setForm({ ...form, education: e.target.value })} />
              </div>
            </div>
          </section>

          {/* Search Locations */}
          <section>
            <div className="flex items-center gap-2 mb-1">
              <MapPin className="w-4 h-4 text-brand-500" />
              <h3 className="text-sm font-semibold t-secondary">Search Locations</h3>
            </div>
            <p className="text-xs t-faint mb-3">
              Add cities you're open to working in. "India" and "Remote" are always included automatically.
              The AI generates targeted queries for each location.
            </p>
            <TagInput
              tags={form.search_locations || []}
              onChange={(tags) => setForm({ ...form, search_locations: tags })}
              placeholder="Add a city (e.g., Mumbai, Bangalore, Hyderabad)..."
              tagClass="bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20"
            />
            <div className="flex gap-2 mt-2">
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                India (always included)
              </span>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400 border border-violet-500/20">
                Remote (always included)
              </span>
            </div>
          </section>

          {/* Core Skills */}
          <section>
            <h3 className="text-sm font-semibold t-secondary mb-1">Core Skills</h3>
            <p className="text-xs t-faint mb-3">Your strongest skills — highest weight in job matching.</p>
            <TagInput tags={form.core_skills || []}
              onChange={(tags) => setForm({ ...form, core_skills: tags })}
              placeholder="Add a core skill (e.g., Spring Boot)..." tagClass="skill-tag" />
          </section>

          {/* Secondary Skills */}
          <section>
            <h3 className="text-sm font-semibold t-secondary mb-1">Secondary Skills</h3>
            <p className="text-xs t-faint mb-3">Skills you know but aren't your primary strength.</p>
            <TagInput tags={form.secondary_skills || []}
              onChange={(tags) => setForm({ ...form, secondary_skills: tags })}
              placeholder="Add a secondary skill..." tagClass="skill-tag-secondary" />
          </section>

          {/* Tools */}
          <section>
            <h3 className="text-sm font-semibold t-secondary mb-1">Tools & Platforms</h3>
            <p className="text-xs t-faint mb-3">IDEs, build tools, platforms.</p>
            <TagInput tags={form.tools || []}
              onChange={(tags) => setForm({ ...form, tools: tags })}
              placeholder="Add a tool (e.g., Docker, Jira)..." tagClass="skill-tag-tool" />
          </section>

          {/* Role Variants */}
          <section>
            <h3 className="text-sm font-semibold t-secondary mb-1">Search Role Variants</h3>
            <p className="text-xs t-faint mb-3">
              Job titles used in search queries. Add titles you'd apply for, remove ones you wouldn't.
            </p>
            <TagInput tags={form.role_variants || []}
              onChange={(tags) => setForm({ ...form, role_variants: tags })}
              placeholder="Add a role (e.g., Backend Engineer)..."
              tagClass="bg-violet-500/10 text-violet-600 dark:text-violet-400 border border-violet-500/20" />
          </section>

          {/* Domain Keywords */}
          <section>
            <h3 className="text-sm font-semibold t-secondary mb-1">Domain Keywords</h3>
            <p className="text-xs t-faint mb-3">Industry terms and patterns.</p>
            <TagInput tags={form.domain_keywords || []}
              onChange={(tags) => setForm({ ...form, domain_keywords: tags })}
              placeholder="Add a keyword (e.g., Microservices)..."
              tagClass="bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20" />
          </section>

          {/* Raw Resume Text */}
          {profile.resume_text && (
            <section>
              <button onClick={() => setShowRawText(!showRawText)}
                className="flex items-center gap-2 text-sm font-semibold t-secondary hover:t-primary transition-colors">
                <FileText className="w-4 h-4" />
                Parsed Resume Text
                {showRawText ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
              {showRawText && (
                <pre className="mt-2 p-3 rounded-lg text-xs t-muted font-mono leading-relaxed overflow-x-auto max-h-48 overflow-y-auto"
                  style={{ backgroundColor: 'var(--bg-elevated)' }}>
                  {profile.resume_text}
                </pre>
              )}
            </section>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-themed">
          <p className="text-xs t-faint">Changes affect future job searches and scoring.</p>
          <div className="flex gap-2">
            <button onClick={onClose} className="btn-secondary">Cancel</button>
            <button onClick={handleSave} disabled={saving} className="btn-primary">
              <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
