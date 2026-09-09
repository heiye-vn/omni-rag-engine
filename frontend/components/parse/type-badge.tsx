import { Badge } from "@/components/ui/badge";
import { ELEMENT_TYPE_COLORS, DEFAULT_TYPE_COLOR } from "@/lib/constants";
import { cn } from "@/lib/utils";

/** Element 类型徽章（heading紫 / paragraph蓝 / table绿 / code灰 / image橙） */
export function TypeBadge({ type, className }: { type: string; className?: string }) {
  return (
    <Badge className={cn(ELEMENT_TYPE_COLORS[type] ?? DEFAULT_TYPE_COLOR, className)}>
      {type}
    </Badge>
  );
}
