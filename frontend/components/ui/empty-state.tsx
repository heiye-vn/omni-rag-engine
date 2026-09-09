import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

/** 引导性空状态：图标徽章 + 标题 + 说明 + 可选主操作 */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex h-full min-h-56 flex-col items-center justify-center gap-3 py-10 text-center", className)}>
      <div className="flex size-12 items-center justify-center rounded-xl bg-brand-50 ring-1 ring-inset ring-brand-100">
        <Icon className="size-5 text-brand-600" />
      </div>
      <div>
        <div className="text-sm font-medium text-stone-700">{title}</div>
        {description && <div className="mt-1 max-w-72 text-xs leading-relaxed text-stone-400">{description}</div>}
      </div>
      {action}
    </div>
  );
}
