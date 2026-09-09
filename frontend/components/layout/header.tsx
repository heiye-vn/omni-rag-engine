"use client";

import { useHealth } from "@/hooks/use-health";
import { cn } from "@/lib/utils";

/** 顶栏：页面区留白 + 引擎在线状态胶囊 */
export function Header() {
  const { data, isError } = useHealth();
  const online = !isError && data?.status === "ok";

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-stone-200/80 bg-white/70 px-6 backdrop-blur">
      <div className="text-[13px] text-stone-500">
        omni-rag-engine <span className="mx-1.5 text-stone-300">/</span> 控制台
      </div>
      <div
        className={cn(
          "flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset",
          online
            ? "bg-brand-50 text-brand-700 ring-brand-200"
            : "bg-red-50 text-red-700 ring-red-200",
        )}
      >
        <span className="relative flex size-2">
          {online && (
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand-400 opacity-60" />
          )}
          <span
            className={cn(
              "relative inline-flex size-2 rounded-full",
              online ? "bg-brand-500" : "bg-red-500",
            )}
          />
        </span>
        {online ? "引擎在线" : "引擎离线"}
      </div>
    </header>
  );
}
