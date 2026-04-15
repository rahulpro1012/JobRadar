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

// ============================================================
// Jobs
// ============================================================

export const getJobs = (params = {}) => api.get('/jobs', { params });

export const getJob = (id) => api.get(`/jobs/${id}`);

export const updateJobStatus = (id, status) =>
  api.patch(`/jobs/${id}/status`, { status });

export const getJobStats = () => api.get('/jobs/stats');

export const refreshJobs = () => api.post('/jobs/refresh');

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

export default api;
