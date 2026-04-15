import { useState, useEffect, useCallback, useRef } from 'react';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import TabBar from './components/TabBar';
import StatsBar from './components/StatsBar';
import JobCard from './components/JobCard';
import JobCardSkeleton from './components/JobCardSkeleton';
import EmptyState from './components/EmptyState';
import SettingsPanel from './components/SettingsPanel';
import * as api from './services/api';

export default function App() {
  // State
  const [profile, setProfile] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState(null);
  const [blacklistCount, setBlacklistCount] = useState(0);
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

  // Load initial data
  useEffect(() => {
    loadInitialData();
  }, []);

  // Reload jobs when tab or filters change
  useEffect(() => {
    if (!loading) loadJobs();
  }, [activeTab, filters]);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      // Check backend health (handles Render cold start)
      await api.checkHealth();

      // Load profile
      try {
        const profileRes = await api.getProfile();
        setProfile(profileRes.data);
      } catch {
        setProfile(null);
      }

      // Load jobs + stats
      await Promise.all([loadJobs(), loadStats(), loadBlacklistCount()]);
    } catch (err) {
      console.error('Failed to connect to backend:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadJobs = async () => {
    try {
      const params = {};
      if (activeTab !== 'all') params.status = activeTab;
      if (filters.minScore > 0) params.min_score = filters.minScore;
      if (filters.days > 0) params.days = filters.days;
      if (filters.sources?.length > 0) params.source = filters.sources[0]; // simplified

      const res = await api.getJobs(params);
      setJobs(res.data.jobs);
      setPagination(res.data.pagination);
    } catch (err) {
      console.error('Failed to load jobs:', err);
    }
  };

  const loadStats = async () => {
    try {
      const res = await api.getJobStats();
      setStats(res.data);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  };

  const loadBlacklistCount = async () => {
    try {
      const res = await api.getBlacklist();
      setBlacklistCount(res.data.total);
    } catch {
      setBlacklistCount(0);
    }
  };

  const handleUpload = async (file) => {
    try {
      const res = await api.uploadResume(file);
      setProfile(res.data.profile);
    } catch (err) {
      alert(err.response?.data?.error || 'Upload failed');
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await api.refreshJobs();
      await Promise.all([loadJobs(), loadStats()]);
    } catch (err) {
      alert(err.response?.data?.error || 'Refresh failed');
    } finally {
      setRefreshing(false);
    }
  };

  const handleStatusChange = async (jobId, status) => {
    try {
      await api.updateJobStatus(jobId, status);
      // Update local state immediately for responsiveness
      setJobs((prev) =>
        prev.map((j) => (j.id === jobId ? { ...j, status } : j))
      );
      loadStats();
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  const handleBlockSource = async (domain) => {
    try {
      await api.addBlacklistEntry('domain', domain);
      loadBlacklistCount();
      loadJobs();
    } catch (err) {
      console.error('Failed to block source:', err);
    }
  };

  const handleBlockCompany = async (company) => {
    try {
      await api.addBlacklistEntry('company', company.toLowerCase());
      loadBlacklistCount();
      loadJobs();
    } catch (err) {
      console.error('Failed to block company:', err);
    }
  };

  const openSettings = (tab) => {
    setSettingsTab(tab || 'quota');
    setSettingsOpen(true);
  };

  return (
    <div className="min-h-screen bg-surface-50">
      <Navbar
        onUpload={handleUpload}
        onRefresh={handleRefresh}
        onSettingsClick={() => openSettings('quota')}
        isRefreshing={refreshing}
        hasProfile={!!profile}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* Stats */}
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
            onManageBlacklist={() => openSettings('blacklist')}
          />

          {/* Content area */}
          <div className="flex-1 min-w-0">
            {/* No profile */}
            {!loading && !profile && (
              <EmptyState
                type="noProfile"
                onAction={() => fileRef.current?.click()}
              />
            )}

            {/* Has profile */}
            {profile && (
              <>
                {/* Profile summary bar */}
                <div className="card px-4 py-3 mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                  <span className="font-medium text-surface-700">
                    {profile.primary_role}
                  </span>
                  <span className="text-surface-400">|</span>
                  <span className="text-surface-500">
                    {profile.experience_years}yr exp
                  </span>
                  <span className="text-surface-400">|</span>
                  <span className="text-surface-500">{profile.location}</span>
                  <span className="text-surface-400">|</span>
                  <div className="flex flex-wrap gap-1">
                    {(profile.core_skills || []).slice(0, 5).map((s) => (
                      <span
                        key={s}
                        className="px-2 py-0.5 text-xs rounded-md bg-brand-50 text-brand-700 font-medium"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Tabs */}
                <TabBar
                  activeTab={activeTab}
                  onTabChange={setActiveTab}
                  counts={stats}
                />

                {/* Job list */}
                <div className="mt-4 space-y-3">
                  {loading ? (
                    <JobCardSkeleton count={4} />
                  ) : jobs.length === 0 ? (
                    <EmptyState
                      type={activeTab === 'new' ? 'noJobs' : 'noResults'}
                      onAction={activeTab === 'new' ? handleRefresh : null}
                    />
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
                  <div className="flex justify-center gap-2 mt-6">
                    {Array.from({ length: pagination.pages }, (_, i) => i + 1).map(
                      (p) => (
                        <button
                          key={p}
                          onClick={() => {
                            setFilters({ ...filters });
                            setPagination({ ...pagination, page: p });
                          }}
                          className={`w-8 h-8 rounded-lg text-sm font-medium ${
                            p === pagination.page
                              ? 'bg-brand-600 text-white'
                              : 'bg-surface-100 text-surface-600 hover:bg-surface-200'
                          }`}
                        >
                          {p}
                        </button>
                      )
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </main>

      {/* Settings Modal */}
      <SettingsPanel
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        initialTab={settingsTab}
      />
    </div>
  );
}
