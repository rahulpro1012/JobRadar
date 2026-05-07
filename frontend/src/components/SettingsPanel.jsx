import { useState, useEffect } from "react";
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
} from "lucide-react";
import * as api from "../services/api";
import { quotaPercent } from "../utils/helpers";

const SETTING_TABS = [
  { key: "quota", label: "API Quota", icon: BarChart3 },
  { key: "companies", label: "Companies", icon: Building2 },
  { key: "blacklist", label: "Blacklist", icon: Ban },
  { key: "preferences", label: "Preferences", icon: SlidersHorizontal },
];

export default function SettingsPanel({ isOpen, onClose, initialTab }) {
  const [tab, setTab] = useState(initialTab || "quota");
  const [quota, setQuota] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [blacklist, setBlacklist] = useState({ entries: [], grouped: {} });
  const [newCompany, setNewCompany] = useState({
    company_name: "",
    careers_url: "",
  });
  const [newBlock, setNewBlock] = useState({ type: "domain", value: "" });

  useEffect(() => {
    if (isOpen) loadData();
  }, [isOpen, tab]);

  const loadData = async () => {
    try {
      if (tab === "quota") {
        const r = await api.getQuota();
        setQuota(r.data.quotas);
      } else if (tab === "companies") {
        const r = await api.getCompanies();
        setCompanies(r.data.companies);
      } else if (tab === "blacklist") {
        const r = await api.getBlacklist();
        setBlacklist(r.data);
      }
    } catch {}
  };

  const handleAddCompany = async () => {
    if (!newCompany.company_name || !newCompany.careers_url) return;
    try {
      await api.addCompany(newCompany);
      setNewCompany({ company_name: "", careers_url: "" });
      loadData();
    } catch (err) {
      alert(err.response?.data?.error || "Failed");
    }
  };

  const handleAddBlock = async () => {
    if (!newBlock.value) return;
    try {
      await api.addBlacklistEntry(newBlock.type, newBlock.value);
      setNewBlock({ ...newBlock, value: "" });
      loadData();
    } catch (err) {
      alert(err.response?.data?.error || "Failed");
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="fixed inset-0 backdrop-blur-sm"
        style={{ backgroundColor: "var(--overlay)" }}
        onClick={onClose}
      />
      <div
        className="relative rounded-2xl shadow-2xl border border-themed w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col"
        style={{ backgroundColor: "var(--bg-card)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-themed">
          <h2 className="font-display font-bold text-lg t-primary">Settings</h2>
          <button onClick={onClose} className="btn-ghost p-1.5">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-themed px-6">
          {SETTING_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t.key
                  ? "border-brand-500 text-brand-600 dark:text-brand-400"
                  : "border-transparent t-muted hover:t-primary"
              }`}
            >
              <t.icon className="w-4 h-4" />
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Quota */}
          {tab === "quota" && quota && (
            <div className="space-y-4">
              {Object.entries(quota).map(([key, q]) => {
                const pct = quotaPercent(q.used, q.daily_limit);
                const isUnlimited = q.daily_limit <= 0;
                return (
                  <div key={key}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-medium t-secondary">
                        {q.source}
                      </span>
                      <span className="t-muted">
                        {isUnlimited
                          ? `${q.used} calls (unlimited)`
                          : `${q.used} / ${q.daily_limit}`}
                      </span>
                    </div>
                    <div
                      className="h-1.5 rounded-full overflow-hidden"
                      style={{ backgroundColor: "var(--bg-elevated)" }}
                    >
                      <div
                        className={`h-full rounded-full transition-all ${
                          pct > 80
                            ? "bg-red-500"
                            : pct > 50
                            ? "bg-amber-500"
                            : "bg-brand-500"
                        }`}
                        style={{
                          width: isUnlimited ? "5%" : `${Math.max(2, pct)}%`,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Companies */}
          {tab === "companies" && (
            <div className="space-y-4">
              <div className="flex gap-2">
                <input
                  className="input flex-1"
                  placeholder="Company name"
                  value={newCompany.company_name}
                  onChange={(e) =>
                    setNewCompany({
                      ...newCompany,
                      company_name: e.target.value,
                    })
                  }
                />
                <input
                  className="input flex-[2]"
                  placeholder="Careers page URL"
                  value={newCompany.careers_url}
                  onChange={(e) =>
                    setNewCompany({
                      ...newCompany,
                      careers_url: e.target.value,
                    })
                  }
                />
                <button
                  onClick={handleAddCompany}
                  className="btn-primary shrink-0"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-2">
                {companies.map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center gap-3 py-2 px-3 rounded-lg border border-themed"
                    style={{ backgroundColor: "var(--bg-elevated)" }}
                  >
                    <button
                      onClick={async () => {
                        await api.toggleCompany(c.id);
                        loadData();
                      }}
                      className="shrink-0"
                    >
                      {c.enabled ? (
                        <ToggleRight className="w-5 h-5 text-brand-500" />
                      ) : (
                        <ToggleLeft className="w-5 h-5 t-faint" />
                      )}
                    </button>
                    <div className="flex-1 min-w-0">
                      <p
                        className={`text-sm font-medium ${
                          c.enabled ? "t-secondary" : "t-faint"
                        }`}
                      >
                        {c.company_name}
                      </p>
                      <p className="text-xs t-faint truncate">
                        {c.careers_url}
                      </p>
                    </div>
                    <button
                      onClick={async () => {
                        await api.removeCompany(c.id);
                        loadData();
                      }}
                      className="btn-ghost p-1.5 text-red-500 hover:bg-red-500/10"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Blacklist */}
          {tab === "blacklist" && (
            <div className="space-y-4">
              <div className="flex gap-2">
                <select
                  className="input w-36"
                  value={newBlock.type}
                  onChange={(e) =>
                    setNewBlock({ ...newBlock, type: e.target.value })
                  }
                >
                  <option value="domain">Domain</option>
                  <option value="company">Company</option>
                  <option value="keyword">Keyword</option>
                </select>
                <input
                  className="input flex-1"
                  placeholder={`Enter ${newBlock.type} to block...`}
                  value={newBlock.value}
                  onChange={(e) =>
                    setNewBlock({ ...newBlock, value: e.target.value })
                  }
                  onKeyDown={(e) => e.key === "Enter" && handleAddBlock()}
                />
                <button
                  onClick={handleAddBlock}
                  className="btn-danger shrink-0"
                >
                  <Ban className="w-4 h-4" /> Block
                </button>
              </div>
              {["domain", "company", "keyword"].map((type) => {
                const items = blacklist.grouped?.[type] || [];
                if (items.length === 0) return null;
                return (
                  <div key={type}>
                    <p className="text-xs font-medium t-faint uppercase tracking-wider mb-2">
                      Blocked {type}s ({items.length})
                    </p>
                    <div className="space-y-1">
                      {items.map((entry) => (
                        <div
                          key={entry.id}
                          className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-red-500/10 border border-red-500/20"
                        >
                          <span className="text-sm text-red-500">
                            {entry.value}
                          </span>
                          <button
                            onClick={async () => {
                              await api.removeBlacklistEntry(entry.id);
                              loadData();
                            }}
                            className="text-red-500/50 hover:text-red-500"
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

          {/* Preferences */}
          {tab === "preferences" && (
            <div className="space-y-4">
              <p className="text-sm t-muted">
                JobRadar learns from your Apply, Save, and Skip actions to
                improve recommendations over time.
              </p>
              <button
                onClick={async () => {
                  if (window.confirm("Reset all preferences?")) {
                    await api.resetPreferences();
                    alert("Reset done.");
                  }
                }}
                className="btn-danger"
              >
                <RotateCcw className="w-4 h-4" /> Reset All Preferences
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
