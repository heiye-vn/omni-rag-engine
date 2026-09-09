import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type Tone = "neutral" | "blue" | "green" | "purple" | "amber" | "red" | "teal" | "gray" | "orange" | "brand" | "ink";

/** 墨青色系徽章：teal/brand 为主角色，purple 重映射为暖石灰（去蓝紫） */
const tones: Record<Tone, string> = {
  neutral: "bg-stone-100 text-stone-600 ring-stone-200",
  brand: "bg-brand-100 text-brand-800 ring-brand-200",
  teal: "bg-brand-50 text-brand-700 ring-brand-200",
  blue: "bg-cyan-50 text-cyan-800 ring-cyan-200",
  green: "bg-green-50 text-green-700 ring-green-200",
  purple: "bg-stone-200/70 text-stone-700 ring-stone-300",
  amber: "bg-accent-50 text-accent-700 ring-accent-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  gray: "bg-stone-100 text-stone-500 ring-stone-200",
  orange: "bg-orange-50 text-orange-800 ring-orange-200",
  ink: "bg-ink text-stone-100 ring-ink",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  /** 左侧状态点 */
  dot?: boolean;
}

export function Badge({ className, tone = "neutral", dot = false, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ring-1 ring-inset",
        tones[tone],
        className,
      )}
      {...props}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}
