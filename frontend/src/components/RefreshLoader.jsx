import { useState, useEffect, useMemo } from 'react';
import { Radar } from 'lucide-react';

function buildStages(profile) {
  const skills = profile?.core_skills || [];
  const role = profile?.primary_role || 'matching roles';
  const location = profile?.location || '';
  const topSkills = skills.slice(0, 3).join(', ') || 'relevant skills';
  const locText = location ? ` in ${location}` : '';

  return [
    { text: "Connecting to job sources...", phase: "Starting" },
    { text: "Scanning Greenhouse job boards...", phase: "Greenhouse" },
    { text: "Checking product companies and startups...", phase: "Greenhouse" },
    { text: `Looking for ${role} positions...`, phase: "Greenhouse" },
    { text: `Matching roles with ${topSkills}...`, phase: "Greenhouse" },
    { text: "Filtering by your experience level...", phase: "Greenhouse" },
    { text: "Moving to Lever job boards...", phase: "Lever" },
    { text: "Scanning enterprise and startup openings...", phase: "Lever" },
    { text: `Finding ${topSkills} opportunities...`, phase: "Lever" },
    { text: "Checking Ashby career boards...", phase: "Ashby" },
    { text: "Pulling compensation data where available...", phase: "Ashby" },
    { text: `Querying Jooble for roles${locText}...`, phase: "Jooble" },
    { text: `Searching for ${role} across India...`, phase: "Jooble" },
    { text: "Aggregating from Naukri, Indeed, and more...", phase: "Jooble" },
    { text: "Fetching Indeed RSS feeds...", phase: "Indeed" },
    { text: `Pulling latest ${topSkills} listings...`, phase: "Indeed" },
    { text: "Querying Google Jobs via SerpApi...", phase: "SerpApi" },
    { text: `Searching "${role}${locText}"...`, phase: "SerpApi" },
    { text: "Generating career page search links...", phase: "Careers" },
    { text: "Building filtered URLs for 20+ companies...", phase: "Careers" },
    { text: "Searching SearxNG for Naukri listings...", phase: "SearxNG" },
    { text: `Querying site:naukri.com for ${role}...`, phase: "SearxNG" },
    { text: "Searching Yahoo for LinkedIn job posts...", phase: "Yahoo" },
    { text: `Finding ${topSkills} roles on job portals...`, phase: "Yahoo" },
    { text: "All sources scanned. Processing results...", phase: "Processing" },
    { text: "Applying blacklist filters...", phase: "Filtering" },
    { text: "Removing duplicate listings across sources...", phase: "Dedup" },
    { text: "Scoring jobs against your profile...", phase: "Scoring" },
    {
      text: `Matching ${topSkills} with job requirements...`,
      phase: "Scoring",
    },
    { text: "Calculating experience fit and recency...", phase: "Scoring" },
    { text: "Ranking by relevance...", phase: "Scoring" },
    { text: "Running AI analysis on top matches...", phase: "AI" },
    { text: "Generating match explanations...", phase: "AI" },
    { text: "Finalizing results...", phase: "Done" },
    { text: "Wrapping up — this can take a moment...", phase: "Waiting" },
    { text: "Still working — almost ready...", phase: "Waiting" },
    { text: "Hang tight — processing a large batch...", phase: "Waiting" },
    { text: "Just a few more seconds...", phase: "Waiting" },
    { text: "Finishing up...", phase: "Waiting" },
  ];
}

export default function RefreshLoader({ profile }) {
  const stages = useMemo(() => buildStages(profile), [profile]);
  const waitStart = stages.length - 5;
  const [stageIndex, setStageIndex] = useState(0);
  const [dots, setDots] = useState('');
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    const stageTimer = setInterval(() => {
      setStageIndex((prev) => {
        if (prev >= waitStart) return waitStart + ((prev - waitStart + 1) % 5);
        return prev + 1;
      });
    }, 3500);
    const dotTimer = setInterval(() => { setDots((p) => (p.length >= 3 ? '' : p + '.')); }, 500);
    const elapsed = setInterval(() => { setElapsedSec((p) => p + 1); }, 1000);
    return () => { clearInterval(stageTimer); clearInterval(dotTimer); clearInterval(elapsed); };
  }, [waitStart]);

  const stage = stages[stageIndex];
  const progress = Math.min(95, ((stageIndex + 1) / waitStart) * 100);
  const minutes = Math.floor(elapsedSec / 60);
  const seconds = elapsedSec % 60;
  const timeStr = minutes > 0 ? `${minutes}m ${seconds.toString().padStart(2, '0')}s` : `${seconds}s`;

  return (
    <div className="flex flex-col items-center justify-center py-16 animate-fade-in">
      <div className="relative mb-8">
        <div className="w-20 h-20 rounded-2xl bg-brand-600/20 flex items-center justify-center radar-pulse">
          <Radar className="w-10 h-10 text-brand-500 animate-radar-sweep" />
        </div>
        <div className="absolute inset-0 w-20 h-20">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-2 w-2 h-2 rounded-full bg-brand-400 animate-pulse" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-2 w-1.5 h-1.5 rounded-full bg-violet-500 animate-pulse-slow" />
          <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-2 w-1.5 h-1.5 rounded-full bg-brand-300 animate-pulse" />
        </div>
      </div>
      <h3 className="font-display font-semibold text-lg t-primary mb-3">Finding your next role{dots}</h3>
      <div className="flex items-center gap-3 mb-5 min-h-[28px]">
        <span className="badge bg-brand-500/15 text-brand-500 border border-brand-500/25 text-xs min-w-[70px] justify-center">{stage.phase}</span>
        <p className="text-sm t-muted animate-fade-in" key={stageIndex}>{stage.text}</p>
      </div>
      <div className="w-72 h-1.5 bg-themed-elevated rounded-full overflow-hidden mb-3">
        <div className="h-full bg-gradient-to-r from-brand-600 via-brand-400 to-brand-500 rounded-full transition-all duration-1000 ease-out"
          style={{ width: `${progress}%` }} />
      </div>
      <div className="flex items-center gap-4 text-xs t-faint">
        <span>Scanning multiple sources</span>
        <span className="w-1 h-1 rounded-full bg-themed-elevated" />
        <span>{timeStr} elapsed</span>
      </div>
    </div>
  );
}
