/**
 * JobRadar API Service
 * Centralized API client for all backend communication.
 */
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  timeout: 120000, // 2 min timeout (Render cold start can take ~60s)
  headers: { 'Content-Type': 'application/json' },
});

// ============================================================
// Health
// ============================================================

export const checkHealth = () => api.get('/health');

// ============================================================
// Profile
// ============================================================

export const getProfile = () => api.get('/profile');

export const uploadResume = (file) => {
  const formData = new FormData();
  formData.append('resume', file);
  return api.post('/profile/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const updateProfile = (data) => api.put('/profile', data);

// A1: Re-parse the stored resume into the v2 tiered schema
export const reparseProfile = () => api.post('/profile/reparse');

// ============================================================
// Jobs
// ============================================================

export const getJobs = (params = {}) => api.get('/jobs', { params });

export const getJob = (id) => api.get(`/jobs/${id}`);

export const getJobAnalysis = (id) => api.get(`/jobs/${id}/analysis`);

export const updateJobStatus = (id, status) =>
  api.patch(`/jobs/${id}/status`, { status });

export const getJobStats = () => api.get('/jobs/stats');

export const refreshJobs = () => api.post('/jobs/refresh');

// Async refresh + polling (real per-source progress)
export const refreshJobsAsync = () => api.post('/jobs/refresh-async');
export const getRefreshStatus = (jobId) => api.get(`/jobs/refresh-async/${jobId}`);
export const getLatestRefresh = () => api.get('/jobs/refresh-async/latest');

// Dismiss feature
export const dismissJob = (id) => api.post(`/jobs/${id}/dismiss`);
export const undismissJob = (id) => api.post(`/jobs/${id}/undismiss`);
export const bulkDismissJobs = (jobIds) => api.post('/jobs/bulk-dismiss', { job_ids: jobIds });
export const bulkUndismissJobs = (jobIds) => api.post('/jobs/bulk-undismiss', { job_ids: jobIds });

// Retention + manual job-table management
export const getRetention = () => api.get('/jobs/retention');
export const setRetention = (days) => api.put('/jobs/retention', { retention_days: days });
export const purgeJobs = (criteria) => api.post('/jobs/purge', criteria);

// ============================================================
// Blacklist
// ============================================================

export const getBlacklist = (type) =>
  api.get('/blacklist', { params: type ? { type } : {} });

export const addBlacklistEntry = (type, value) =>
  api.post('/blacklist', { type, value });

export const removeBlacklistEntry = (id) => api.delete(`/blacklist/${id}`);

// ============================================================
// Settings
// ============================================================

export const getQuota = () => api.get('/settings/quota');

export const getCompanies = () => api.get('/settings/companies');

export const addCompany = (data) => api.post('/settings/companies', data);

export const removeCompany = (id) => api.delete(`/settings/companies/${id}`);

export const toggleCompany = (id) =>
  api.patch(`/settings/companies/${id}/toggle`);

// ============================================================
// Preferences
// ============================================================

export const getPreferences = () => api.get('/preferences');

export const resetPreferences = () => api.post('/preferences/reset');

// ============================================================
// Admin — source health
// ============================================================

export const getSourceHealth = () => api.get('/admin/source-health');

export const resetSourceHealth = (source) =>
  api.post(`/admin/source-health/${source}/reset`);

// ============================================================
// Email scanner (Feature 1)
// ============================================================

export const getEmailStatus = () => api.get('/email/status');
export const testEmail = () => api.post('/email/test');
export const scanEmailAsync = () => api.post('/email/scan-async');
export const getEmailSenders = () => api.get('/email/senders');
export const addEmailSender = (value) => api.post('/email/senders', { value });
export const removeEmailSender = (id) => api.delete(`/email/senders/${id}`);
export const toggleEmailSender = (id) => api.patch(`/email/senders/${id}/toggle`);
export const setEmailScanDays = (days) => api.put('/email/scan-days', { scan_days: days });

export default api;
