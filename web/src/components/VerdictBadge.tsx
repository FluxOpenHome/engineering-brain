"use client";

import type { Tone } from "./ui";
import { Badge } from "./ui";

export const VERDICT_TONE: Record<string, Tone> = {
  compliant: "green",
  non_compliant: "red",
  partial: "amber",
  insufficient_evidence: "grey",
  unverified: "purple",
  not_applicable: "slate",
};

export function VerdictBadge({ verdict, className = "" }: { verdict: string | null | undefined; className?: string }) {
  if (!verdict) return <span className="text-xs text-slate-400">–</span>;
  return (
    <Badge tone={VERDICT_TONE[verdict] ?? "slate"} className={className}>
      {verdict.replace(/_/g, " ")}
    </Badge>
  );
}
