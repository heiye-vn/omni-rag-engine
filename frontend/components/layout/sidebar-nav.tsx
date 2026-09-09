"use client";

import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Database, FileSearch, LayoutDashboard, Scissors } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "仪表盘", icon: LayoutDashboard, desc: "引擎状态与任务" },
  { href: "/parse", label: "解析工作台", icon: FileSearch, desc: "文档结构化解析" },
  { href: "/chunk-lab", label: "切块实验室", icon: Scissors, desc: "四策略对比" },
  { href: "/kb", label: "知识库检索", icon: Database, desc: "入库与召回测试" },
] as const;

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1">
      {NAV_ITEMS.map(({ href, label, icon: Icon, desc }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors",
              active
                ? "bg-white/10 text-white"
                : "text-brand-200/70 hover:bg-white/5 hover:text-brand-50",
            )}
          >
            {/* 激活态左侧墨青指示条 */}
            <span
              className={cn(
                "absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-brand-300 transition-opacity",
                active ? "opacity-100" : "opacity-0",
              )}
            />
            <Icon className={cn("size-4 shrink-0", active ? "text-brand-300" : "text-brand-200/50 group-hover:text-brand-200")} />
            <span className="min-w-0">
              <span className="block text-[13px] font-medium leading-tight">{label}</span>
              <span className={cn(
                "block text-[11px] leading-tight",
                active ? "text-brand-200/80" : "text-brand-200/40",
              )}>
                {desc}
              </span>
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
