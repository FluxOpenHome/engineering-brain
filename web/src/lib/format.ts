export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtPages(start: number | null | undefined, end: number | null | undefined): string {
  if (start == null && end == null) return "";
  if (end == null || end === start) return `p.${start}`;
  return `pp.${start}-${end}`;
}

export function pct(x: number | null | undefined): string {
  if (x == null) return "";
  return `${Math.round(x * 100)}%`;
}

export function citationLabel(c: {
  doc_number?: string | null;
  title?: string | null;
  revision?: string | null;
  clause_id?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  source?: string | null;
}): string {
  const bits: string[] = [];
  bits.push(c.doc_number || c.title || c.source || "source");
  if (c.revision) bits.push(`Rev ${c.revision}`);
  if (c.clause_id) bits.push(`cl. ${c.clause_id}`);
  const p = fmtPages(c.page_start, c.page_end);
  if (p) bits.push(p);
  return bits.join(" ");
}

export function splitCsv(s: string): string[] {
  return s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

export function slugify(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9/\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^\/+|\/+$/g, "");
}

export function fmtQuantity(
  q:
    | {
        value?: number | null;
        min?: number | null;
        max?: number | null;
        unit?: string | null;
        comparator?: string | null;
      }
    | null
    | undefined,
): string {
  if (!q) return "";
  const unit = q.unit ? ` ${q.unit}` : "";
  if (q.min != null && q.max != null) return `${q.min}–${q.max}${unit}`;
  if (q.value != null) return `${q.comparator ? `${q.comparator} ` : ""}${q.value}${unit}`;
  if (q.min != null) return `≥ ${q.min}${unit}`;
  if (q.max != null) return `≤ ${q.max}${unit}`;
  return JSON.stringify(q);
}
