import { useState, useEffect } from "react";
import {
  X,
  BarChart3,
  Ban,
  SlidersHorizontal,
  Trash2,
  RotateCcw,
  Activity,
  Database,
  Save,
  AlertTriangle,
  Mail,
  Plus,
} from "lucide-react";
import * as api from "../services/api";
import { quotaPercent, sourceHealthColor, sourceName } from "../utils/helpers";
import { toast } from "./Toast";

const SETTING_TABS = [
  { key: "quota", label: "API Quota", icon: BarChart3 },
  { key: "sources", label: "Sources", icon: Activity },
  { key: "email", label: "Email", icon: Mail },
  { key: "blacklist", label: "Blacklist", icon: Ban },
  { key: "managejobs", label: "Manage Jobs", icon: Database },
  { key: "preferences", label: "Preferences", icon: SlidersHorizontal },
];

// Two-click themed confirm — avoids native window.confirm().
function ConfirmButton({ id, confirmKey, setConfirmKey, onConfirm, className = "btn-danger text-xs", disabled = false, children }) {
  if (confirmKey === id) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <button
          onClick={() => { setConfirmKey(null); onConfirm(); }}
          className="btn-danger text-xs"
        >
          Confirm
        </button>
        <button onClick={() => setConfirmKey(null)} className="btn-ghost text-xs">
          Cancel
        </button>
      </span>
    );
  }
  return (
    <button disabled={disabled} onClick={() => setConfirmKey(id)} className={className}>
      {children}
    </button>
  );
}

export default function SettingsPanel({ isOpen, onClose, initialTab, onJobsChanged }) {
  const [tab, setTab] = useState(initialTab || "quota");
  const [quota, setQuota] = useState(null);
  const [sourceHealth, setSourceHealth] = useState([]);
  const [blacklist, setBlacklist] = useState({ entries: [], grouped: {} });
  const [retentionDays, setRetentionDays] = useState(15);
  const [jobSources, setJobSources] = useState({});
  const [purgeStatus, setPurgeStatus] = useState("archived");
  const [purgeSource, setPurgeSource] = useState("");
  const [newBlock, setNewBlock] = useState({ type: "domain", value: "" });
  const [confirmKey, setConfirmKey] = useState(null);
  const [emailStatus, setEmailStatus] = useState(null);
  const [senders, setSenders] = useState([]);
  const [newSender, setNewSender] = useState("");
  const [scanDays, setScanDays] = useState(7);

  // Jump to the requested tab whenever the panel is (re)opened
  useEffect(() => {
    if (isOpen && initialTab) setTab(initialTab);
  }, [isOpen, initialTab]);

  useEffect(() => {
    if (isOpen) {
      setConfirmKey(null);
      loadData();
    }
  }, [isOpen, tab]);

  const loadData = async () => {
    try {
      if (tab === "quota") {
        const r = await api.getQuota();
        setQuota(r.data.quotas);
      } else if (tab === "sources") {
        const r = await api.getSourceHealth();
        setSourceHealth(r.data.sources || []);
      } else if (tab === "managejobs") {
        const [ret, stats] = await Promise.all([
          api.getRetention(),
          api.getJobStats(),
        ]);
        setRetentionDays(ret.data.retention_days ?? 15);
        setJobSources(stats.data.by_source || {});
      } else if (tab === "blacklist") {
        const r = await api.getBlacklist();
        setBlacklist(r.data);
      } else if (tab === "email") {
        const [st, sn] = await Promise.all([
          api.getEmailStatus(),
          api.getEmailSenders(),
        ]);
        setEmailStatus(st.data);
        setSenders(sn.data.senders || []);
        setScanDays(st.data.scan_days ?? 7);
      }
    } catch {}
  };

  const handleTestEmail = async () => {
    try {
      const r = await api.testEmail();
      if (r.data.ok) toast.success("Connected to Gmail ✓");
      else toast.error(r.data.error || "Connection failed");
    } catch {
      toast.error("Connection test failed");
    }
  };

  const handleAddSender = async () => {
    if (!newSender.trim()) return;
    try {
      const r = await api.addEmailSender(newSender.trim());
      setSenders(r.data.senders);
      setNewSender("");
    } catch (err) {
      toast.error(err.response?.data?.error || "Failed to add sender");
    }
  };

  const handleRemoveSender = async (id) => {
    try {
      const r = await api.removeEmailSender(id);
      setSenders(r.data.senders);
    } catch {}
  };

  const handleToggleSender = async (id) => {
    try {
      const r = await api.toggleEmailSender(id);
      setSenders(r.data.senders);
    } catch {}
  };

  const handleSaveScanDays = async () => {
    try {
      const r = await api.setEmailScanDays(parseInt(scanDays) || 7);
      setScanDays(r.data.scan_days);
      toast.success("Scan window updated");
    } catch (err) {
      toast.error(err.response?.data?.error || "Failed to save");
    }
  };

  const handleAddBlock = async () => {
    if (!newBlock.value) return;
    try {
      await api.addBlacklistEntry(newBlock.type, newBlock.value);
      setNewBlock({ ...newBlock, value: "" });
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.error || "Failed to add blacklist entry");
    }
  };

  const handleSaveRetention = async () => {
    try {
      const r = await api.setRetention(parseInt(retentionDays) || 0);
      setRetentionDays(r.data.retention_days);
      toast.success(`Retention set to ${r.data.retention_days} days`);
    } catch (err) {
      toast.error(err.response?.data?.error || "Failed to save retention");
    }
  };

  const handlePurge = async (criteria) => {
    try {
      const r = await api.purgeJobs(criteria);
      toast.success(`Deleted ${r.data.deleted} jobs`);
      onJobsChanged?.();
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.error || "Purge failed");
    }
  };

  const handleResetPrefs = async () => {
    try {
      await api.resetPreferences();
      toast.success("Preferences reset");
    } catch (err) {
      toast.error("Reset failed");
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
        className="relative rounded-2xl shadow-2xl border border-themed w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col"
        style={{ backgroundColor: "var(--bg-card)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-themed">
          <h2 className="font-display font-bold text-lg t-primary">Settings</h2>
          <button onClick={onClose} className="btn-ghost p-1.5">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body: sidebar rail + content */}
        <div className="flex flex-col sm:flex-row flex-1 min-h-0">
          {/* Tab rail (vertical on desktop, horizontal scroll on mobile) */}
          <nav className="flex sm:flex-col gap-1 p-2 sm:w-44 shrink-0 overflow-x-auto sm:overflow-y-auto border-b sm:border-b-0 sm:border-r border-themed">
            {SETTING_TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium shrink-0 whitespace-nowrap transition-colors ${
                  tab === t.key
                    ? "bg-brand-500/10 text-brand-600 dark:text-brand-400"
                    : "t-muted hover:t-primary hover:bg-themed-elevated"
                }`}
              >
                <t.icon className="w-4 h-4 shrink-0" />
                {t.label}
              </button>
            ))}
          </nav>

          {/* Content */}
          <div className="flex-1 min-h-0 overflow-y-auto p-6">
            {/* Quota */}
            {tab === "quota" && quota && (
              <div className="space-y-4">
                {Object.entries(quota).map(([key, q]) => {
                  const pct = quotaPercent(q.used, q.daily_limit);
                  const isUnlimited = q.daily_limit <= 0;
                  return (
                    <div key={key}>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="font-medium t-secondary">{q.source}</span>
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
                            pct > 80 ? "bg-red-500" : pct > 50 ? "bg-amber-500" : "bg-brand-500"
                          }`}
                          style={{ width: isUnlimited ? "5%" : `${Math.max(2, pct)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Source health */}
            {tab === "sources" && (
              <div className="space-y-2">
                {sourceHealth.length === 0 && (
                  <p className="text-sm t-muted">No source health data yet. Run a refresh first.</p>
                )}
                {sourceHealth.map((s) => {
                  const status = s.status || "healthy";
                  return (
                    <div
                      key={s.source}
                      className="flex items-center gap-3 py-2 px-3 rounded-lg border border-themed"
                      style={{ backgroundColor: "var(--bg-elevated)" }}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium t-secondary truncate">{s.source}</span>
                          <span className={`badge text-xs ${sourceHealthColor(status)}`}>
                            {status.replace("_", " ")}
                          </span>
                        </div>
                        <p className="text-xs t-faint truncate">
                          {s.jobs_returned_last_run ?? 0} jobs last run
                          {s.consecutive_failures > 0 && ` · ${s.consecutive_failures} fails in a row`}
                          {s.last_failure_reason && ` · ${s.last_failure_reason}`}
                        </p>
                      </div>
                      {status !== "healthy" && (
                        <button
                          onClick={async () => {
                            try {
                              await api.resetSourceHealth(s.source);
                              loadData();
                            } catch {}
                          }}
                          className="btn-ghost text-xs shrink-0"
                          title="Reset circuit breaker"
                        >
                          <RotateCcw className="w-3.5 h-3.5" /> Reset
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Email scanner */}
            {tab === "email" && (
              <div className="space-y-5">
                {/* Status + test */}
                <div className="flex items-center gap-2 flex-wrap">
                  {emailStatus?.enabled ? (
                    <span className="badge bg-emerald-500/15 text-emerald-500 border border-emerald-500/25">
                      Credentials detected
                    </span>
                  ) : (
                    <span className="badge bg-amber-500/15 text-amber-500 border border-amber-500/25">
                      Not configured
                    </span>
                  )}
                  {emailStatus?.address && (
                    <span className="text-sm t-muted">{emailStatus.address}</span>
                  )}
                  <button onClick={handleTestEmail} className="btn-ghost text-xs ml-auto">
                    <Activity className="w-3.5 h-3.5" /> Test connection
                  </button>
                </div>

                {!emailStatus?.enabled && (
                  <p className="text-xs t-faint">
                    Set <code className="text-brand-500">GMAIL_ADDRESS</code> and{" "}
                    <code className="text-brand-500">GMAIL_APP_PASSWORD</code> in the backend
                    environment (like your Groq key) to enable scanning.
                  </p>
                )}
                {emailStatus?.last_scan && (
                  <p className="text-xs t-faint">
                    Last scan: {String(emailStatus.last_scan).slice(0, 16).replace("T", " ")} ·
                    imported {emailStatus.last_imported ?? 0}
                  </p>
                )}

                {/* Scan window */}
                <div className="pt-3 border-t border-themed">
                  <p className="text-sm font-semibold t-secondary mb-1">Scan window</p>
                  <p className="text-xs t-faint mb-2">Look back this many days for alert emails.</p>
                  <div className="flex items-center gap-2">
                    <input
                      type="number" min="1" max="90"
                      className="input w-24"
                      value={scanDays}
                      onChange={(e) => setScanDays(e.target.value)}
                    />
                    <span className="text-sm t-muted">days</span>
                    <button onClick={handleSaveScanDays} className="btn-primary text-xs ml-2">
                      <Save className="w-3.5 h-3.5" /> Save
                    </button>
                  </div>
                </div>

                {/* Sender allowlist */}
                <div className="pt-3 border-t border-themed">
                  <p className="text-sm font-semibold t-secondary mb-1">Allowed senders</p>
                  <p className="text-xs t-faint mb-2">
                    Only emails from these domains/addresses are scanned — nothing else in your inbox is read.
                  </p>
                  <div className="flex gap-2 mb-3">
                    <input
                      className="input flex-1"
                      placeholder="e.g. linkedin.com"
                      value={newSender}
                      onChange={(e) => setNewSender(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleAddSender()}
                    />
                    <button onClick={handleAddSender} className="btn-primary shrink-0">
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="space-y-1">
                    {senders.map((s) => (
                      <div
                        key={s.id}
                        className="flex items-center gap-3 py-1.5 px-3 rounded-lg border border-themed"
                        style={{ backgroundColor: "var(--bg-elevated)" }}
                      >
                        <input
                          type="checkbox"
                          checked={!!s.enabled}
                          onChange={() => handleToggleSender(s.id)}
                          className="w-4 h-4 accent-brand-600 cursor-pointer shrink-0"
                          title={s.enabled ? "Enabled" : "Disabled"}
                        />
                        <span className={`text-sm flex-1 ${s.enabled ? "t-secondary" : "t-faint line-through"}`}>
                          {s.value}
                        </span>
                        <button
                          onClick={() => handleRemoveSender(s.id)}
                          className="text-red-500/50 hover:text-red-500"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
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
                    onKeyDown={(e) => e.key === "Enter" && handleAddBlock()}
                  />
                  <button onClick={handleAddBlock} className="btn-danger shrink-0">
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
                            <span className="text-sm text-red-500">{entry.value}</span>
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

            {/* Manage Jobs */}
            {tab === "managejobs" && (
              <div className="space-y-6">
                {/* Retention window */}
                <div>
                  <p className="text-sm font-semibold t-secondary mb-1">Auto-cleanup window</p>
                  <p className="text-xs t-faint mb-2">
                    Jobs older than this (by fetched date) are deleted at the end of every refresh. Set 0 to disable.
                  </p>
                  <div className="flex items-center gap-2">
                    <input
                      type="number" min="0" max="365"
                      className="input w-24"
                      value={retentionDays}
                      onChange={(e) => setRetentionDays(e.target.value)}
                    />
                    <span className="text-sm t-muted">days</span>
                    <button onClick={handleSaveRetention} className="btn-primary text-xs ml-2">
                      <Save className="w-3.5 h-3.5" /> Save
                    </button>
                  </div>
                </div>

                {/* Purge older than now */}
                <div className="pt-4 border-t border-themed">
                  <p className="text-sm font-semibold t-secondary mb-2">One-off cleanup</p>
                  <ConfirmButton
                    id="purge-old"
                    confirmKey={confirmKey}
                    setConfirmKey={setConfirmKey}
                    className="btn-secondary text-xs"
                    onConfirm={() => handlePurge({ older_than_days: parseInt(retentionDays) || 15 })}
                  >
                    <Trash2 className="w-3.5 h-3.5" /> Purge older than {parseInt(retentionDays) || 15} days now
                  </ConfirmButton>
                </div>

                {/* Clear by status */}
                <div className="pt-4 border-t border-themed">
                  <p className="text-sm font-semibold t-secondary mb-2">Clear by status</p>
                  <div className="flex gap-2 items-center">
                    <select
                      className="input w-40"
                      value={purgeStatus}
                      onChange={(e) => setPurgeStatus(e.target.value)}
                    >
                      {["new", "archived", "skipped", "dismissed", "saved", "applied"].map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                    <ConfirmButton
                      id="purge-status"
                      confirmKey={confirmKey}
                      setConfirmKey={setConfirmKey}
                      onConfirm={() => handlePurge({ status: purgeStatus })}
                    >
                      <Trash2 className="w-3.5 h-3.5" /> Clear
                    </ConfirmButton>
                  </div>
                </div>

                {/* Clear by source */}
                {Object.keys(jobSources).length > 0 && (
                  <div className="pt-4 border-t border-themed">
                    <p className="text-sm font-semibold t-secondary mb-2">Clear by source</p>
                    <div className="flex gap-2 items-center">
                      <select
                        className="input flex-1"
                        value={purgeSource}
                        onChange={(e) => setPurgeSource(e.target.value)}
                      >
                        <option value="">Select a source…</option>
                        {Object.entries(jobSources).map(([domain, count]) => (
                          <option key={domain} value={domain}>
                            {sourceName(domain)} ({count})
                          </option>
                        ))}
                      </select>
                      <ConfirmButton
                        id="purge-source"
                        confirmKey={confirmKey}
                        setConfirmKey={setConfirmKey}
                        disabled={!purgeSource}
                        onConfirm={() => handlePurge({ source: purgeSource })}
                      >
                        <Trash2 className="w-3.5 h-3.5" /> Clear
                      </ConfirmButton>
                    </div>
                  </div>
                )}

                {/* Clear ALL */}
                <div className="pt-4 border-t border-themed">
                  <div className="flex items-start gap-2 mb-2">
                    <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                    <p className="text-xs t-muted">
                      Danger zone — permanently delete every job (including saved &amp; applied).
                    </p>
                  </div>
                  <ConfirmButton
                    id="purge-all"
                    confirmKey={confirmKey}
                    setConfirmKey={setConfirmKey}
                    onConfirm={() => handlePurge({ all: true, confirm: true })}
                  >
                    <Trash2 className="w-3.5 h-3.5" /> Clear ALL jobs
                  </ConfirmButton>
                </div>
              </div>
            )}

            {/* Preferences */}
            {tab === "preferences" && (
              <div className="space-y-4">
                <p className="text-sm t-muted">
                  JobRadar learns from your Apply, Save, and Skip actions to improve recommendations over time.
                </p>
                <ConfirmButton
                  id="reset-prefs"
                  confirmKey={confirmKey}
                  setConfirmKey={setConfirmKey}
                  className="btn-danger"
                  onConfirm={handleResetPrefs}
                >
                  <RotateCcw className="w-4 h-4" /> Reset All Preferences
                </ConfirmButton>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
