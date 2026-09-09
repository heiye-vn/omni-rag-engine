import { cn } from "@/lib/utils";
import type { ButtonHTMLAttributes } from "react";

type Variant = "default" | "accent" | "outline" | "ghost" | "destructive";
type Size = "default" | "sm" | "xs";

const variants: Record<Variant, string> = {
  default: "bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800 shadow-xs",
  accent: "bg-accent-600 text-white hover:bg-accent-700 active:bg-accent-800 shadow-xs",
  outline: "border border-stone-300 bg-white text-stone-700 hover:bg-brand-50 hover:border-brand-300 hover:text-brand-700",
  ghost: "bg-transparent text-stone-600 hover:bg-stone-100 hover:text-stone-900",
  destructive: "bg-red-600 text-white hover:bg-red-700 shadow-xs",
};

const sizes: Record<Size, string> = {
  default: "h-9 px-4 text-sm",
  sm: "h-8 px-3 text-xs",
  xs: "h-7 px-2.5 text-xs",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export function Button({ className, variant = "default", size = "default", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1",
        "disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  );
}
