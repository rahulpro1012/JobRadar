import { useRef, useState } from 'react';
import {
  Radar,
  Upload,
  RefreshCw,
  Settings,
  Loader2,
} from 'lucide-react';

export default function Navbar({ onUpload, onRefresh, onSettingsClick, isRefreshing, hasProfile }) {
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await onUpload(file);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-surface-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center">
            <Radar className="w-5 h-5 text-white" />
          </div>
          <span className="font-display font-bold text-xl tracking-tight text-surface-900">
            JobRadar
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {/* Upload Resume */}
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="btn-secondary"
          >
            {uploading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Upload className="w-4 h-4" />
            )}
            <span className="hidden sm:inline">
              {hasProfile ? 'Update Resume' : 'Upload Resume'}
            </span>
          </button>

          {/* Refresh Jobs */}
          <button
            onClick={onRefresh}
            disabled={isRefreshing || !hasProfile}
            className="btn-primary"
            title={!hasProfile ? 'Upload a resume first' : 'Refresh jobs'}
          >
            {isRefreshing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            <span className="hidden sm:inline">Refresh</span>
          </button>

          {/* Settings */}
          <button onClick={onSettingsClick} className="btn-ghost">
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
