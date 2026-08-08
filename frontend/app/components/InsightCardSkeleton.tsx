export default function InsightCardSkeleton() {
  return (
    <div className="relative rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden animate-pulse">
      <div className="absolute left-0 top-0 bottom-0 w-1 bg-slate-700" />
      <div className="pl-5 pr-4 py-4 space-y-4">
        <div>
          <div className="h-2.5 w-24 bg-slate-800 rounded mb-2" />
          <div className="h-3 w-full bg-slate-800 rounded mb-1.5" />
          <div className="h-3 w-4/5 bg-slate-800 rounded" />
        </div>
        <div className="border-t border-slate-800 pt-4">
          <div className="h-2.5 w-16 bg-slate-800 rounded mb-2" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="h-12 bg-slate-800/60 rounded-lg" />
            <div className="h-12 bg-slate-800/60 rounded-lg" />
            <div className="h-12 bg-slate-800/60 rounded-lg" />
            <div className="h-12 bg-slate-800/60 rounded-lg" />
          </div>
        </div>
        <div className="border-t border-slate-800 pt-4">
          <div className="h-2.5 w-20 bg-slate-800 rounded mb-2" />
          <div className="h-3 w-3/4 bg-slate-800 rounded" />
        </div>
      </div>
    </div>
  );
}
