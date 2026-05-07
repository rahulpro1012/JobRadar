import { useRef, useState } from 'react';
import { Radar, Upload, RefreshCw, Settings, Loader2, Sun, Moon } from 'lucide-react';
import { useTheme } from '../utils/ThemeContext';

export default function Navbar({ onUpload, onRefresh, onSettingsClick, isRefreshing, hasProfile }) {
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const { theme, toggle } = useTheme();

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try { await onUpload(file); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ''; }
  };

  return (
    <header className="sticky top-0 z-30 border-b border-themed" style={{ backgroundColor: 'var(--bg-primary)', backdropFilter: 'blur(12px)', opacity: 0.95 }}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 sm:h-16 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center">
            <Radar className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
          </div>
          <div>
            <span className="font-display font-bold text-base sm:text-lg tracking-tight t-primary">
              JobRadar
            </span>
            <span className="hidden md:inline text-xs t-faint ml-2">Personal Job Dashboard</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 sm:gap-2">
          <input ref={fileRef} type="file" accept=".pdf,.docx" className="hidden" onChange={handleFileChange} />

          {/* Theme toggle */}
          <button onClick={toggle} className="btn-ghost p-2" title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
            {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>

          <button onClick={() => fileRef.current?.click()} disabled={uploading} className="btn-secondary text-xs sm:text-sm">
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            <span className="hidden sm:inline">{hasProfile ? 'Update Resume' : 'Upload Resume'}</span>
          </button>

          <button onClick={onRefresh} disabled={isRefreshing || !hasProfile} className="btn-primary text-xs sm:text-sm"
            title={!hasProfile ? 'Upload a resume first' : 'Refresh jobs'}>
            {isRefreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span className="hidden sm:inline">Refresh</span>
          </button>

          <button onClick={onSettingsClick} className="btn-ghost p-2">
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
