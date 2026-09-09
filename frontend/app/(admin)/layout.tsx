import { Header } from "@/components/layout/header";
import { SidebarNav } from "@/components/layout/sidebar-nav";

/** 控制台 App Shell：深墨青侧边栏 + 顶栏 + 暖纸白内容区 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col bg-brand-950 px-3 py-5">
        {/* Logo 区 */}
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <div className="flex size-8 items-center justify-center rounded-lg bg-brand-600 text-[13px] font-semibold text-white">
            R
          </div>
          <div>
            <div className="text-[13px] font-semibold leading-tight text-white">omni-rag-engine</div>
            <div className="text-[11px] leading-tight text-brand-200/50">v0.1.0 · FastAPI</div>
          </div>
        </div>
        <SidebarNav />
        {/* 底部说明 */}
        <div className="mt-auto rounded-lg bg-white/5 p-3 text-[11px] leading-relaxed text-brand-200/50">
          全模态 RAG 基础设施引擎
          <br />
          解析 · 清洗 · 切块 · 检索
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex-1 overflow-x-auto bg-paper p-6">{children}</main>
      </div>
    </div>
  );
}
