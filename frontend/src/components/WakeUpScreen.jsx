import { Radar, Loader2 } from 'lucide-react';

export default function WakeUpScreen() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-themed p-4">
      <div className="relative mb-8">
        <div className="w-20 h-20 rounded-2xl bg-brand-600/20 flex items-center justify-center radar-pulse">
          <Radar className="w-10 h-10 text-brand-500" />
        </div>
      </div>
      <h1 className="font-display font-bold text-2xl t-primary mb-2">JobRadar</h1>
      <p className="t-muted text-sm mb-6 text-center max-w-xs">
        Waking up the server... This takes about a minute on the first visit.
      </p>
      <Loader2 className="w-6 h-6 text-brand-500 animate-spin" />
    </div>
  );
}
