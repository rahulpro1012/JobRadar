import { useState, useEffect, useRef } from 'react';
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
import ToastContainer, { toast } from './components/Toast';
import * as api from './services/api';

export default function App() {
  // Connection state
  const [connected, setConnected] = useState(false);
  const [waking, setWaking] = useState(true);

  // Data state
  const [profile, setProfile] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState(null);
  const [blacklistCount, setBlacklistCount] = useState(0);

  // UI state
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState('new');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState('quota');
  const [filters, setFilters] = useState({
    sources: [],
    minScore: 0,
    days: 0,
  });
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0 });

  const fileRef = useRef(null);

  // ── Boot sequence ──
  useEffect(() => {
    wakeUpBackend();
  }, []);

  // ── Reload jobs on tab/filter change ──
  useEffect(() => {
    if (connected) loadJobs();
  }, [activeTab, filters, connected]);

  // ── Wake up Render backend ──
  const wakeUpBackend = async () => {
    setWaking(true);
    const maxRetries = 3;
    for (let i = 0; i < maxRetries; i++) {
      try {
        await api.checkHealth();
        setConnected(true);
        setWaking(false);
        await loadInitialData();
        return;
      } catch {
        if (i < maxRetries - 1) {
          await new Promise((r) => setTimeout(r, 3000));
        }
      }
    }
    setWaking(false);
    toast.error('Could not connect to backend. Please refresh the page.');
  };

  // ── Load all initial data ──
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
    } catch (err) {
      console.error('Init error:', err);
    } finally {
      setLoading(false);
    }
  };

  // ── Load jobs with current filters ──
  const loadJobs = async () => {
    try {
      const params = { page: pagination.page, per_page: 20 };
      if (activeTab !== 'all') params.status = activeTab;
      if (filters.minScore > 0) params.min_score = filters.minScore;
      if (filters.days > 0) params.days = filters.days;
      if (filters.sources?.length > 0) params.source = filters.sources[0];

      const res = await api.getJobs(params);
      setJobs(res.data.jobs);
      setPagination(res.data.pagination);
    } catch (err) {
      console.error('Load jobs error:', err);
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

  // ── Actions ──
  const handleUpload = async (file) => {
    try {
      const res = await api.uploadResume(file);
      setProfile(res.data.profile);
      toast.success('Resume parsed successfully!');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Upload failed');
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const res = await api.refreshJobs();
      const d = res.data;
      await Promise.all([loadJobs(), loadStats()]);

      const parts = [];
      if (d.new_jobs > 0) parts.push(`${d.new_jobs} new`);
      if (d.filtered > 0) parts.push(`${d.filtered} filtered`);
      if (d.deduplicated > 0) parts.push(`${d.deduplicated} deduped`);
      if (d.scored > 0) parts.push(`${d.scored} scored`);

      toast.success(parts.length > 0 ? parts.join(' · ') : 'No new jobs found');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Refresh failed');
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
      if (status === 'applied') toast.success('Marked as applied');
      if (status === 'saved') toast.info('Job saved');
    } catch {}
  };

  const handleBlockSource = async (domain) => {
    try {
      await api.addBlacklistEntry('domain', domain);
      loadBlacklistCount();
      loadJobs();
      toast.info(`Blocked source: ${domain}`);
    } catch {}
  };

  const handleBlockCompany = async (company) => {
    try {
      await api.addBlacklistEntry('company', company.toLowerCase());
      loadBlacklistCount();
      loadJobs();
      toast.info(`Blocked company: ${company}`);
    } catch {}
  };

  const handlePageChange = (page) => {
    setPagination((prev) => ({ ...prev, page }));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Show wake-up screen while connecting to Render
  if (waking) return <WakeUpScreen />;

  return (
    <div className="min-h-screen bg-surface-50">
      <Navbar
        onUpload={handleUpload}
        onRefresh={handleRefresh}
        onSettingsClick={() => { setSettingsTab('quota'); setSettingsOpen(true); }}
        isRefreshing={refreshing}
        hasProfile={!!profile}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* Stats bar */}
        {stats && stats.total > 0 && (
          <div className="mb-6">
            <StatsBar stats={stats} />
          </div>
        )}

        {/* Main layout */}
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Sidebar */}
          <Sidebar
            filters={filters}
            onFilterChange={setFilters}
            blacklistCount={blacklistCount}
            onManageBlacklist={() => { setSettingsTab('blacklist'); setSettingsOpen(true); }}
          />

          {/* Content */}
          <div className="flex-1 min-w-0">
            {/* No profile state */}
            {!loading && !profile && (
              <EmptyState type="noProfile" onAction={() => fileRef.current?.click()} />
            )}

            {/* Has profile */}
            {profile && (
              <>
                <ProfileCard profile={profile} onProfileUpdate={(p) => setProfile(p)} />

                <TabBar
                  activeTab={activeTab}
                  onTabChange={(tab) => {
                    setActiveTab(tab);
                    setPagination((p) => ({ ...p, page: 1 }));
                  }}
                  counts={stats}
                />

                {/* Empty state for first-time users */}
                {!loading && stats?.total === 0 && (
                  <div className="mt-4">
                    <EmptyState type="noJobs" onAction={handleRefresh} />
                  </div>
                )}

                {/* Job list */}
                <div className="mt-4 space-y-3">
                  {loading ? (
                    <JobCardSkeleton count={4} />
                  ) : jobs.length === 0 && stats?.total > 0 ? (
                    <EmptyState type="noResults" />
                  ) : (
                    jobs.map((job) => (
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
                {pagination.pages > 1 && (
                  <div className="flex justify-center gap-2 mt-6 mb-4">
                    <button
                      onClick={() => handlePageChange(Math.max(1, pagination.page - 1))}
                      disabled={pagination.page <= 1}
                      className="btn-ghost text-sm"
                    >
                      Previous
                    </button>
                    {Array.from({ length: Math.min(pagination.pages, 7) }, (_, i) => {
                      let page;
                      if (pagination.pages <= 7) {
                        page = i + 1;
                      } else if (pagination.page <= 4) {
                        page = i + 1;
                      } else if (pagination.page >= pagination.pages - 3) {
                        page = pagination.pages - 6 + i;
                      } else {
                        page = pagination.page - 3 + i;
                      }
                      return (
                        <button
                          key={page}
                          onClick={() => handlePageChange(page)}
                          className={`w-9 h-9 rounded-lg text-sm font-medium transition-colors ${
                            page === pagination.page
                              ? 'bg-brand-600 text-white'
                              : 'bg-surface-100 text-surface-600 hover:bg-surface-200'
                          }`}
                        >
                          {page}
                        </button>
                      );
                    })}
                    <button
                      onClick={() => handlePageChange(Math.min(pagination.pages, pagination.page + 1))}
                      disabled={pagination.page >= pagination.pages}
                      className="btn-ghost text-sm"
                    >
                      Next
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </main>

      {/* Hidden file input for EmptyState upload action */}
      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.docx"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleUpload(file);
          e.target.value = '';
        }}
      />

      <SettingsPanel
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        initialTab={settingsTab}
      />

      <ToastContainer />
    </div>
  );
}
