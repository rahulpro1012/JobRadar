export default function JobCardSkeleton({ count = 3 }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card p-4 animate-pulse">
          <div className="flex justify-between mb-2">
            <div className="skeleton h-5 w-48" />
            <div className="skeleton h-5 w-12 rounded-full" />
          </div>
          <div className="skeleton h-4 w-36 mb-3" />
          <div className="flex gap-2 mb-3">
            <div className="skeleton h-5 w-16 rounded-md" />
            <div className="skeleton h-5 w-20 rounded-md" />
            <div className="skeleton h-5 w-14 rounded-md" />
          </div>
          <div className="skeleton h-4 w-full mb-1" />
          <div className="skeleton h-4 w-3/4 mb-3" />
          <div className="flex gap-2 pt-2 border-t border-surface-100">
            <div className="skeleton h-8 w-20 rounded-lg" />
            <div className="skeleton h-8 w-16 rounded-lg" />
            <div className="skeleton h-8 w-16 rounded-lg" />
          </div>
        </div>
      ))}
    </>
  );
}
