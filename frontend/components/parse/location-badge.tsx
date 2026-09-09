import { Badge } from "@/components/ui/badge";
import type { Location } from "@/lib/types";

/**
 * Location 溯源徽章：按定位字段存在性自动选择展示形态
 * - 行号（Markdown/TXT/CSV）：L12-L18
 * - 页码+bbox（PDF/PPTX/OCR）：第 3 页 · bbox
 * - DOM selector（HTML/DOCX）：selector 路径
 * - 时间戳（音视频 ASR）：12.3s ~ 15.8s
 */
export function LocationBadge({ location }: { location?: Location }) {
  if (!location) return null;

  if (location.start_line != null) {
    const end = location.end_line;
    return <Badge tone="blue">{end != null ? `L${location.start_line}-L${end}` : `L${location.start_line}`}</Badge>;
  }

  if (location.page_number != null) {
    const bbox = location.bbox;
    return (
      <Badge tone="blue">
        第 {location.page_number} 页
        {bbox ? ` · bbox[${bbox.map((v) => Math.round(v * 100) / 100).join(", ")}]` : ""}
      </Badge>
    );
  }

  if (location.selector) {
    return <Badge tone="blue" className="max-w-40 truncate" title={location.selector}>{location.selector}</Badge>;
  }

  if (location.start_time != null) {
    const fmt = (t: number) => `${t.toFixed(1)}s`;
    return (
      <Badge tone="blue">
        {location.end_time != null ? `${fmt(location.start_time)} ~ ${fmt(location.end_time)}` : fmt(location.start_time)}
      </Badge>
    );
  }

  return null;
}
