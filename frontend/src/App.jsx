import { useState, useEffect, useRef, useMemo } from 'react';
import { Loader2 } from 'lucide-react';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import TabBar from './components/TabBar';
import StatsBar from './components/StatsBar';
import JobCard from './components/JobCard';
import JobCardSkeleton from './components/JobCardSkeleton';
import EmptyState from './components/EmptyState';
import SettingsPanel from './components/SettingsPanel';
import ProfileCard from './components/ProfileCard';
import WakeUpScreen from './components/WakeUpScreen';
import RefreshLoader from './components/RefreshLoader';
import SearchBar from './components/SearchBar';
import ToastContainer, { toast } from './components/Toast';
import * as api from './services/api';
import ScrollToTop from "./components/ScrollToTop";
import LastRefreshed from "./components/LastRefreshed";
import ProfileEditor from "./components/ProfileEditor";
import BulkActionBar from "./components/BulkActionBar";

export default function App() {
  const [connected, setConnected] = useState(false);
  const [waking, setWaking] = useState(true);
  const [profile, setProfile] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState(null);
  const [blacklistCount, setBlacklistCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState("new");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState("quota");
  const [currentPage, setCurrentPage] = useState(1);
  const [filters, setFilters] = useState({ sources: [], minScore: 0, days: 0 });
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0 });
  const [searchQuery, setSearchQuery] = useState("");
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState(() => {
    try {
      const t = window.localStorage.getItem("jobradar-last-refresh");
      return t ? parseInt(t) : null;
    } catch {
      return null;
    }
  });
  const [profileEditorOpen, setProfileEditorOpen] = useState(false);
  const [refreshProgress, setRefreshProgress] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [showDismissed, setShowDismissed] = useState(false);
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [emailScanning, setEmailScanning] = useState(false);

  const fileRef = useRef(null);
  const pollRef = useRef(null);

  useEffect(() => {
    wakeUpBackend();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);
  useEffect(() => {
    if (connected) loadJobs();
  }, [activeTab, filters, connected, currentPage, showDismissed]);

  // Client-side search filter
  const filteredJobs = useMemo(() => {
    if (!searchQuery.trim()) return jobs;
    const q = searchQuery.toLowerCase();
    return jobs.filter(
      (job) =>
        (job.title || "").toLowerCase().includes(q) ||
        (job.company || "").toLowerCase().includes(q) ||
        (job.location || "").toLowerCase().includes(q) ||
        (job.description_snippet || "").toLowerCase().includes(q) ||
        (Array.isArray(job.skills_found) &&
          job.skills_found.some((s) => s.toLowerCase().includes(q)))
    );
  }, [jobs, searchQuery]);

  const wakeUpBackend = async () => {
    setWaking(true);
    for (let i = 0; i < 3; i++) {
      try {
        await api.checkHealth();
        setConnected(true);
        setWaking(false);
        await loadInitialData();
        return;
      } catch {
        if (i < 2) await new Promise((r) => setTimeout(r, 3000));
      }
    }
    setWaking(false);
    toast.error("Could not connect to backend. Please refresh the page.");
  };

  const loadInitialData = async () => {
    setLoading(true);
    try {
      try {
        const res = await api.getProfile();
        setProfile(res.data);
      } catch {
        setProfile(null);
      }
      await Promise.all([loadJobs(), loadStats(), loadBlacklistCount()]);

      // Email scanner availability (enables the navbar button)
      try {
        const es = await api.getEmailStatus();
        setEmailEnabled(!!es.data?.enabled);
      } catch {}

      // Reconnect to an in-flight job (e.g. page reloaded mid-run).
      // Use the non-blocking pill so a reload never takes over the screen.
      try {
        const latest = await api.getLatestRefresh();
        const st = latest.data?.status;
        if (st === "running" || st === "pending" || st === "ai_scoring") {
          startPolling(latest.data.job_id, true);
        }
      } catch {}
    } finally {
      setLoading(false);
    }
  };

  const loadJobs = async () => {
    try {
      const params = { page: currentPage, per_page: 20 };
      if (activeTab !== "all") params.status = activeTab;
      if (filters.minScore > 0) params.min_score = filters.minScore;
      if (filters.days > 0) params.days = filters.days;
      if (filters.sources?.length > 0) params.source = filters.sources[0];
      if (filters.viaEmail) params.via_email = true;
      if (showDismissed) params.include_dismissed = true;
      const res = await api.getJobs(params);
      setJobs(res.data.jobs);
      setPagination(res.data.pagination);
    } catch (err) {
      console.error("Load jobs error:", err);
    }
  };

  const loadStats = async () => {
    try {
      const res = await api.getJobStats();
      setStats(res.data);
    } catch {}
  };
  const loadBlacklistCount = async () => {
    try {
      const res = await api.getBlacklist();
      setBlacklistCount(res.data.total);
    } catch {}
  };

  const handleUpload = async (file) => {
    try {
      const res = await api.uploadResume(file);
      setProfile(res.data.profile);
      const method = res.data.parse_method === "ai" ? "AI" : "regex";
      toast.success(`Resume parsed successfully (${method})`);
      handleRefresh();
    } catch (err) {
      toast.error(err.response?.data?.error || "Upload failed");
    }
  };

  // Poll an async job until it completes/fails.
  // background=false → full-screen RefreshLoader (used by Refresh).
  // background=true  → non-blocking; jobs stay visible, a pill shows, and a
  //                    "Refresh view" toast appears on completion (used by Email scan).
  const startPolling = (jobId, background = false) => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (background) setEmailScanning(true);
    else setRefreshing(true);

    const cleanup = () => {
      clearInterval(pollRef.current);
      pollRef.current = null;
      if (background) setEmailScanning(false);
      else { setRefreshing(false); setRefreshProgress(null); }
    };

    const finish = async (data) => {
      cleanup();
      if (data?.status === "failed") {
        toast.error(data.error_message || (background ? "Email scan failed" : "Refresh failed"));
        return;
      }
      const newN = data?.jobs_new || 0;
      const aiN = data?.jobs_ai_scored || 0;
      if (background) {
        // Don't disrupt what the user is viewing — offer a reload instead.
        const msg = newN > 0 ? `Email scan done — ${newN} new` : "Email scan done — no new jobs";
        toast(msg, "success", 8000, {
          label: "Refresh view",
          onClick: () => { loadJobs(); loadStats(); },
        });
      } else {
        await new Promise((r) => setTimeout(r, 400)); // let commits settle
        await Promise.all([loadJobs(), loadStats()]);
        const now = Date.now();
        setLastRefreshedAt(now);
        try {
          window.localStorage.setItem("jobradar-last-refresh", String(now));
        } catch {}
        const parts = [];
        if (newN > 0) parts.push(`${newN} new`);
        if (aiN > 0) parts.push(`${aiN} AI-scored`);
        if (data?.duration_sec) parts.push(`${data.duration_sec}s`);
        toast.success(parts.length > 0 ? parts.join(" · ") : "Refresh complete");
      }
    };

    const tick = async () => {
      try {
        const res = await api.getRefreshStatus(jobId);
        const d = res.data;
        if (!background) setRefreshProgress(d);
        if (d.status === "completed" || d.status === "failed") {
          await finish(d);
        }
      } catch (err) {
        cleanup();  // 404 (job gone) or transient error — stop gracefully
      }
    };

    tick();
    pollRef.current = setInterval(tick, background ? 3000 : 2000);
  };

  const handleRefresh = async () => {
    if (refreshing || emailScanning) return;
    setRefreshProgress(null);
    setRefreshing(true);
    try {
      const res = await api.refreshJobsAsync();
      startPolling(res.data.job_id, false);
    } catch (err) {
      setRefreshing(false);
      toast.error(err.response?.data?.error || "Refresh failed to start");
    }
  };

  const handleScanEmail = async () => {
    if (refreshing || emailScanning) return;
    setEmailScanning(true);
    try {
      const res = await api.scanEmailAsync();
      toast.info("Scanning your job-alert emails in the background…");
      startPolling(res.data.job_id, true);
    } catch (err) {
      setEmailScanning(false);
      toast.error(err.response?.data?.error || "Email scan failed to start");
    }
  };

  const handleStatusChange = async (jobId, status) => {
    try {
      await api.updateJobStatus(jobId, status);
      setJobs((prev) =>
        prev.map((j) => (j.id === jobId ? { ...j, status } : j))
      );
      loadStats();
      if (status === "applied") toast.success("Marked as applied");
      if (status === "saved") toast.info("Job saved");
    } catch {}
  };

  const handleBlockSource = async (domain) => {
    try {
      await api.addBlacklistEntry("domain", domain);
      loadBlacklistCount();
      loadJobs();
      toast.info(`Blocked: ${domain}`);
    } catch {}
  };
  const handleBlockCompany = async (company) => {
    try {
      await api.addBlacklistEntry("company", company.toLowerCase());
      loadBlacklistCount();
      loadJobs();
      toast.info(`Blocked: ${company}`);
    } catch {}
  };

  // ── Dismiss feature ──
  const handleDismiss = async (job) => {
    const jobId = job.id;
    // Optimistic: remove from the visible list
    setJobs((prev) => prev.filter((j) => j.id !== jobId));
    try {
      await api.dismissJob(jobId);
      loadStats();
      toast(
        `Dismissed "${(job.title || "job").slice(0, 40)}"`,
        "info",
        5000,
        {
          label: "Undo",
          onClick: async () => {
            try {
              await api.undismissJob(jobId);
              await Promise.all([loadJobs(), loadStats()]);
            } catch {
              toast.error("Couldn't undo");
            }
          },
        }
      );
    } catch {
      // Roll back optimistic removal
      await loadJobs();
      toast.error("Failed to dismiss — please try again");
    }
  };

  const handleUndismiss = async (jobId) => {
    try {
      await api.undismissJob(jobId);
      await Promise.all([loadJobs(), loadStats()]);
    } catch {
      toast.error("Failed to restore");
    }
  };

  const toggleSelected = (jobId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  };
  const clearSelection = () => setSelectedIds(new Set());

  const handleBulkDismiss = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    setJobs((prev) => prev.filter((j) => !selectedIds.has(j.id)));
    clearSelection();
    try {
      const res = await api.bulkDismissJobs(ids);
      loadStats();
      toast(
        `Dismissed ${res.data.dismissed_count} jobs`,
        "info",
        5000,
        {
          label: "Undo",
          onClick: async () => {
            try {
              await api.bulkUndismissJobs(ids);
              await Promise.all([loadJobs(), loadStats()]);
            } catch {
              toast.error("Couldn't undo");
            }
          },
        }
      );
    } catch {
      await loadJobs();
      toast.error("Bulk dismiss failed — please try again");
    }
  };

  const handlePageChange = (page) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (waking) return <WakeUpScreen />;

  return (
    <div className="min-h-screen bg-themed">
      <Navbar
        onUpload={handleUpload}
        onRefresh={handleRefresh}
        onScanEmail={handleScanEmail}
        emailEnabled={emailEnabled}
        scanning={emailScanning}
        busy={refreshing || emailScanning}
        onSettingsClick={() => {
          setSettingsTab("quota");
          setSettingsOpen(true);
        }}
        isRefreshing={refreshing}
        hasProfile={!!profile}
      />

      <main className="max-w-7xl mx-auto px-3 sm:px-6 py-4 sm:py-6">
        {/* Stats */}
        {stats && stats.total > 0 && !refreshing && (
          <div className="mb-4 sm:mb-6">
            <StatsBar stats={stats} />
          </div>
        )}

        {lastRefreshedAt && !refreshing && (
          <LastRefreshed
            timestamp={lastRefreshedAt}
            onRefresh={handleRefresh}
            isRefreshing={refreshing}
          />
        )}

        {/* Main layout — stacks on mobile, side-by-side on desktop */}
        <div className="flex flex-col lg:flex-row gap-4 sm:gap-6">
          {/* Sidebar — mobile: collapsible toggle, desktop: always visible */}
          <div className="lg:hidden">
            <button
              onClick={() => setMobileFilterOpen(!mobileFilterOpen)}
              className="btn-secondary w-full justify-center mb-3"
            >
              {mobileFilterOpen ? "Hide Filters" : "Show Filters"}
            </button>
            {mobileFilterOpen && (
              <Sidebar
                filters={filters}
                onFilterChange={setFilters}
                blacklistCount={blacklistCount}
                onManageBlacklist={() => {
                  setSettingsTab("blacklist");
                  setSettingsOpen(true);
                }}
                showDismissed={showDismissed}
                onToggleDismissed={() => { setShowDismissed((v) => !v); setCurrentPage(1); }}
                dismissedCount={stats?.dismissed || 0}
                availableSources={stats?.by_source || {}}
              />
            )}
          </div>
          <div className="hidden lg:block">
            <Sidebar
              filters={filters}
              onFilterChange={setFilters}
              blacklistCount={blacklistCount}
              onManageBlacklist={() => {
                setSettingsTab("blacklist");
                setSettingsOpen(true);
              }}
              showDismissed={showDismissed}
              onToggleDismissed={() => { setShowDismissed((v) => !v); setCurrentPage(1); }}
              dismissedCount={stats?.dismissed || 0}
              availableSources={stats?.by_source || {}}
            />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            {!loading && !profile && (
              <EmptyState
                type="noProfile"
                onAction={() => fileRef.current?.click()}
              />
            )}

            {profile && (
              <>
                <ProfileCard
                  profile={profile}
                  onClick={() => setProfileEditorOpen(true)}
                />

                {refreshing ? (
                  <RefreshLoader profile={profile} progress={refreshProgress} />
                ) : (
                  <>
                    <TabBar
                      activeTab={activeTab}
                      onTabChange={(tab) => {
                        setActiveTab(tab);
                        setCurrentPage(1);
                        setSearchQuery("");
                      }}
                      counts={stats}
                    />

                    {/* Search bar */}
                    {stats?.total > 0 && (
                      <div className="mt-4">
                        <SearchBar
                          value={searchQuery}
                          onChange={setSearchQuery}
                        />
                      </div>
                    )}

                    {!loading && stats?.total === 0 && (
                      <div className="mt-4">
                        <EmptyState type="noJobs" onAction={handleRefresh} />
                      </div>
                    )}

                    {/* Bulk action bar (appears when jobs are selected) */}
                    <BulkActionBar
                      selectedCount={selectedIds.size}
                      onDismissAll={handleBulkDismiss}
                      onClear={clearSelection}
                    />

                    <div className="space-y-3">
                      {loading ? (
                        <JobCardSkeleton count={4} />
                      ) : filteredJobs.length === 0 ? (
                        <EmptyState
                          type={
                            searchQuery
                              ? "noResults"
                              : stats?.total > 0
                              ? "noResults"
                              : "noJobs"
                          }
                          onAction={
                            !searchQuery && stats?.total === 0
                              ? handleRefresh
                              : null
                          }
                        />
                      ) : (
                        filteredJobs.map((job) => (
                          <JobCard
                            key={job.id}
                            job={job}
                            onStatusChange={handleStatusChange}
                            onBlockSource={handleBlockSource}
                            onBlockCompany={handleBlockCompany}
                            onDismiss={handleDismiss}
                            onUndismiss={handleUndismiss}
                            selected={selectedIds.has(job.id)}
                            onToggleSelect={toggleSelected}
                          />
                        ))
                      )}
                    </div>

                    {/* Pagination */}
                    {pagination.pages > 1 && !searchQuery && (
                      <div className="flex justify-center gap-1.5 sm:gap-2 mt-6 mb-4 flex-wrap">
                        <button
                          onClick={() =>
                            handlePageChange(Math.max(1, currentPage - 1))
                          }
                          disabled={currentPage <= 1}
                          className="btn-ghost text-xs sm:text-sm"
                        >
                          Prev
                        </button>
                        {Array.from(
                          { length: Math.min(pagination.pages, 5) },
                          (_, i) => {
                            let page;
                            if (pagination.pages <= 5) page = i + 1;
                            else if (currentPage <= 3) page = i + 1;
                            else if (currentPage >= pagination.pages - 2)
                              page = pagination.pages - 4 + i;
                            else page = currentPage - 2 + i;
                            return (
                              <button
                                key={page}
                                onClick={() => handlePageChange(page)}
                                className={`w-8 h-8 sm:w-9 sm:h-9 rounded-lg text-xs sm:text-sm font-medium transition-all ${
                                  page === currentPage
                                    ? "bg-brand-600 text-white"
                                    : "btn-secondary"
                                }`}
                              >
                                {page}
                              </button>
                            );
                          }
                        )}
                        <button
                          onClick={() =>
                            handlePageChange(
                              Math.min(pagination.pages, currentPage + 1)
                            )
                          }
                          disabled={currentPage >= pagination.pages}
                          className="btn-ghost text-xs sm:text-sm"
                        >
                          Next
                        </button>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      </main>

      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.docx"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleUpload(f);
          e.target.value = "";
        }}
      />

      <ProfileEditor
        isOpen={profileEditorOpen}
        onClose={() => setProfileEditorOpen(false)}
        profile={profile}
        onProfileUpdate={(p) => setProfile(p)}
      />

      <SettingsPanel
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        initialTab={settingsTab}
        onJobsChanged={() => { loadJobs(); loadStats(); }}
      />
      {/* Background email-scan indicator (non-blocking) */}
      {emailScanning && (
        <div className="fixed bottom-4 left-4 z-40 flex items-center gap-2 px-3 py-2 rounded-xl bg-themed-card border border-themed shadow-lg animate-fade-in">
          <Loader2 className="w-4 h-4 animate-spin text-brand-500" />
          <span className="text-sm t-secondary">Scanning email…</span>
        </div>
      )}

      <ToastContainer />
      <ScrollToTop />
    </div>
  );
}
