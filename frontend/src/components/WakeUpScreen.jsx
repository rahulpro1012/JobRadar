import { Radar, Loader2 } from 'lucide-react';

export default function WakeUpScreen() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-surface-50 p-4">
      <div className="w-16 h-16 rounded-2xl bg-brand-600 flex items-center justify-center mb-6 animate-pulse">
        <Radar className="w-8 h-8 text-white" />
      </div>
      <h1 className="font-display font-bold text-2xl text-surface-900 mb-2">
        JobRadar
      </h1>
      <p className="text-surface-500 text-sm mb-6 text-center max-w-xs">
        Waking up the server... This takes about a minute on the first visit.
      </p>
      <Loader2 className="w-6 h-6 text-brand-500 animate-spin" />
    </div>
  );
}
