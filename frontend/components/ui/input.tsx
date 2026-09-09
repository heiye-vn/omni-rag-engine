import { cn } from "@/lib/utils";
import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";

const fieldClass =
  "h-9 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm text-ink shadow-xs " +
  "placeholder:text-stone-400 transition-colors " +
  "hover:border-stone-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(fieldClass, className)} {...props} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(fieldClass, "px-2", className)} {...props} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-stone-200/80", className)} />;
}
