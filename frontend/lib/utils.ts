/** 简易 class 合并工具（shadcn cn 的零依赖替代） */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
