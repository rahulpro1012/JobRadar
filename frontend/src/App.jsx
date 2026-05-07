import { useState, useEffect, useRef, useMemo } from 'react';
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

  const fileRef = useRef(null);

  useEffect(() => {
    wakeUpBackend();
  }, []);
  useEffect(() => {
    if (connected) loadJobs();
  }, [activeTab, filters, connected, currentPage]);

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

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const res = await api.refreshJobs();
      const d = res.data;
      await Promise.all([loadJobs(), loadStats()]);
      const now = Date.now();
      setLastRefreshedAt(now);
      try {
        window.localStorage.setItem("jobradar-last-refresh", String(now));
      } catch {}
      const parts = [];
      if (d.new_jobs > 0) parts.push(`${d.new_jobs} new`);
      if (d.filtered > 0) parts.push(`${d.filtered} filtered`);
      if (d.deduplicated > 0) parts.push(`${d.deduplicated} deduped`);
      if (d.scored > 0) parts.push(`${d.scored} scored`);
      if (d.ai_scored > 0) parts.push(`${d.ai_scored} AI-scored`);
      toast.success(parts.length > 0 ? parts.join(" · ") : "No new jobs found");
    } catch (err) {
      toast.error(err.response?.data?.error || "Refresh failed");
    } finally {
      setRefreshing(false);
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
                  <RefreshLoader profile={profile} />
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
      />
      <ToastContainer />
      <ScrollToTop />
    </div>
  );
}
