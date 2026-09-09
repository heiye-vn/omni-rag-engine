"use client";

import { cn } from "@/lib/utils";
import { createContext, useContext, useState, type ReactNode } from "react";

interface TabsContextValue {
  value: string;
  setValue: (v: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

/** 受控或非受控均可的轻量 Tabs（shadcn Tabs 的零依赖替代） */
export function Tabs({
  value: controlled,
  defaultValue,
  onValueChange,
  className,
  children,
}: {
  value?: string;
  defaultValue?: string;
  onValueChange?: (v: string) => void;
  className?: string;
  children: ReactNode;
}) {
  const [internal, setInternal] = useState(defaultValue ?? "");
  const value = controlled ?? internal;

  const setValue = (v: string) => {
    setInternal(v);
    onValueChange?.(v);
  };

  return (
    <TabsContext.Provider value={{ value, setValue }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={cn("flex flex-wrap gap-1 border-b border-stone-200", className)}
      role="tablist"
    >
      {children}
    </div>
  );
}

export function TabsTrigger({ value, className, children }: { value: string; className?: string; children: ReactNode }) {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("TabsTrigger 必须在 Tabs 内使用");
  const active = ctx.value === value;

  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => ctx.setValue(value)}
      className={cn(
        "-mb-px border-b-2 px-4 py-2 text-xs font-medium transition-colors",
        active
          ? "border-brand-600 text-brand-700"
          : "border-transparent text-stone-500 hover:text-stone-800 hover:border-stone-300",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({ value, className, children }: { value: string; className?: string; children: ReactNode }) {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("TabsContent 必须在 Tabs 内使用");
  if (ctx.value !== value) return null;
  return <div className={className}>{children}</div>;
}
