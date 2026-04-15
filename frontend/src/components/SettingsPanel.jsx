import { useState, useEffect } from 'react';
import {
  X,
  BarChart3,
  Building2,
  Ban,
  SlidersHorizontal,
  Plus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  RotateCcw,
} from 'lucide-react';
import * as api from '../services/api';
import { quotaPercent } from '../utils/helpers';

const SETTING_TABS = [
  { key: 'quota', label: 'API Quota', icon: BarChart3 },
  { key: 'companies', label: 'Companies', icon: Building2 },
  { key: 'blacklist', label: 'Blacklist', icon: Ban },
  { key: 'preferences', label: 'Preferences', icon: SlidersHorizontal },
];

export default function SettingsPanel({ isOpen, onClose, initialTab }) {
  const [tab, setTab] = useState(initialTab || 'quota');
  const [quota, setQuota] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [blacklist, setBlacklist] = useState({ entries: [], grouped: {} });
  const [newCompany, setNewCompany] = useState({ company_name: '', careers_url: '' });
  const [newBlock, setNewBlock] = useState({ type: 'domain', value: '' });

  useEffect(() => {
    if (!isOpen) return;
    loadData();
  }, [isOpen, tab]);

  const loadData = async () => {
    try {
      if (tab === 'quota') {
        const r = await api.getQuota();
        setQuota(r.data.quotas);
      } else if (tab === 'companies') {
        const r = await api.getCompanies();
        setCompanies(r.data.companies);
      } else if (tab === 'blacklist') {
        const r = await api.getBlacklist();
        setBlacklist(r.data);
      }
    } catch (err) {
      console.error('Settings load error:', err);
    }
  };

  const handleAddCompany = async () => {
    if (!newCompany.company_name || !newCompany.careers_url) return;
    try {
      await api.addCompany(newCompany);
      setNewCompany({ company_name: '', careers_url: '' });
      loadData();
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to add company');
    }
  };

  const handleAddBlock = async () => {
    if (!newBlock.value) return;
    try {
      await api.addBlacklistEntry(newBlock.type, newBlock.value);
      setNewBlock({ ...newBlock, value: '' });
      loadData();
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to add entry');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-200">
          <h2 className="font-display font-bold text-lg">Settings</h2>
          <button onClick={onClose} className="btn-ghost p-1.5">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-surface-200 px-6">
          {SETTING_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t.key
                  ? 'border-brand-600 text-brand-700'
                  : 'border-transparent text-surface-500 hover:text-surface-700'
              }`}
            >
              <t.icon className="w-4 h-4" />
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Quota Tab */}
          {tab === 'quota' && quota && (
            <div className="space-y-4">
              {Object.entries(quota).map(([key, q]) => {
                const pct = quotaPercent(q.used, q.daily_limit);
                const isUnlimited = q.daily_limit <= 0;
                return (
                  <div key={key}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-medium text-surface-700">{q.source}</span>
                      <span className="text-surface-500">
                        {isUnlimited ? `${q.used} calls (unlimited)` : `${q.used} / ${q.daily_limit}`}
                      </span>
                    </div>
                    <div className="h-2 bg-surface-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-amber-500' : 'bg-brand-500'
                        }`}
                        style={{ width: isUnlimited ? '5%' : `${Math.max(2, pct)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Companies Tab */}
          {tab === 'companies' && (
            <div className="space-y-4">
              {/* Add form */}
              <div className="flex gap-2">
                <input
                  className="input flex-1"
                  placeholder="Company name"
                  value={newCompany.company_name}
                  onChange={(e) => setNewCompany({ ...newCompany, company_name: e.target.value })}
                />
                <input
                  className="input flex-[2]"
                  placeholder="Careers page URL"
                  value={newCompany.careers_url}
                  onChange={(e) => setNewCompany({ ...newCompany, careers_url: e.target.value })}
                />
                <button onClick={handleAddCompany} className="btn-primary shrink-0">
                  <Plus className="w-4 h-4" />
                </button>
              </div>
              {/* List */}
              <div className="space-y-2">
                {companies.map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center gap-3 py-2 px-3 rounded-lg bg-surface-50"
                  >
                    <button
                      onClick={async () => {
                        await api.toggleCompany(c.id);
                        loadData();
                      }}
                      className="shrink-0"
                      title={c.enabled ? 'Disable' : 'Enable'}
                    >
                      {c.enabled ? (
                        <ToggleRight className="w-5 h-5 text-brand-600" />
                      ) : (
                        <ToggleLeft className="w-5 h-5 text-surface-400" />
                      )}
                    </button>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium ${c.enabled ? 'text-surface-800' : 'text-surface-400'}`}>
                        {c.company_name}
                      </p>
                      <p className="text-xs text-surface-400 truncate">{c.careers_url}</p>
                    </div>
                    <button
                      onClick={async () => {
                        await api.removeCompany(c.id);
                        loadData();
                      }}
                      className="btn-ghost p-1.5 text-red-500 hover:bg-red-50"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Blacklist Tab */}
          {tab === 'blacklist' && (
            <div className="space-y-4">
              {/* Add form */}
              <div className="flex gap-2">
                <select
                  className="input w-36"
                  value={newBlock.type}
                  onChange={(e) => setNewBlock({ ...newBlock, type: e.target.value })}
                >
                  <option value="domain">Domain</option>
                  <option value="company">Company</option>
                  <option value="keyword">Keyword</option>
                </select>
                <input
                  className="input flex-1"
                  placeholder={`Enter ${newBlock.type} to block...`}
                  value={newBlock.value}
                  onChange={(e) => setNewBlock({ ...newBlock, value: e.target.value })}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddBlock()}
                />
                <button onClick={handleAddBlock} className="btn-danger shrink-0">
                  <Ban className="w-4 h-4" />
                  Block
                </button>
              </div>
              {/* List by type */}
              {['domain', 'company', 'keyword'].map((type) => {
                const items = blacklist.grouped?.[type] || [];
                if (items.length === 0) return null;
                return (
                  <div key={type}>
                    <p className="text-xs font-medium text-surface-500 uppercase tracking-wider mb-2">
                      Blocked {type}s ({items.length})
                    </p>
                    <div className="space-y-1">
                      {items.map((entry) => (
                        <div
                          key={entry.id}
                          className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-red-50"
                        >
                          <span className="text-sm text-red-700">{entry.value}</span>
                          <button
                            onClick={async () => {
                              await api.removeBlacklistEntry(entry.id);
                              loadData();
                            }}
                            className="text-red-400 hover:text-red-600"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Preferences Tab */}
          {tab === 'preferences' && (
            <div className="space-y-4">
              <p className="text-sm text-surface-500">
                JobRadar learns from your Apply, Save, and Skip actions to improve job
                recommendations over time. Reset preferences to start fresh.
              </p>
              <button
                onClick={async () => {
                  if (window.confirm('Reset all learned preferences? This cannot be undone.')) {
                    await api.resetPreferences();
                    alert('Preferences reset successfully.');
                  }
                }}
                className="btn-danger"
              >
                <RotateCcw className="w-4 h-4" />
                Reset All Preferences
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
