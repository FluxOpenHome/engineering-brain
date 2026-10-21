"use client";

import { diffLines, type Change } from "diff";
import { useMemo, useState } from "react";
import { Button } from "./ui";

interface Row {
  left?: { n: number; text: string };
  right?: { n: number; text: string };
  kind: "same" | "add" | "del";
}

function buildRows(changes: Change[]): Row[] {
  const rows: Row[] = [];
  let l = 1;
  let r = 1;
  // Pair consecutive removed/added blocks for side-by-side alignment.
  for (let i = 0; i < changes.length; i++) {
    const c = changes[i];
    const lines = c.value.replace(/\n$/, "").split("\n");
    if (c.removed && changes[i + 1]?.added) {
      const nxt = changes[i + 1];
      const nl = nxt.value.replace(/\n$/, "").split("\n");
      const m = Math.max(lines.length, nl.length);
      for (let k = 0; k < m; k++) {
        rows.push({
          kind: k < lines.length && k < nl.length ? "del" : k < lines.length ? "del" : "add",
          left: k < lines.length ? { n: l++, text: lines[k] } : undefined,
          right: k < nl.length ? { n: r++, text: nl[k] } : undefined,
        });
      }
      i++;
    } else if (c.removed) {
      for (const t of lines) rows.push({ kind: "del", left: { n: l++, text: t } });
    } else if (c.added) {
      for (const t of lines) rows.push({ kind: "add", right: { n: r++, text: t } });
    } else {
      for (const t of lines)
        rows.push({ kind: "same", left: { n: l++, text: t }, right: { n: r++, text: t } });
    }
  }
  return rows;
}

const cellBg = {
  same: "",
  add: "bg-emerald-50",
  del: "bg-red-50",
};

export function DiffView({
  oldText,
  newText,
  defaultMode = "split",
}: {
  oldText: string;
  newText: string;
  defaultMode?: "split" | "unified";
}) {
  const [mode, setMode] = useState<"split" | "unified">(defaultMode);
  const changes = useMemo(() => diffLines(oldText ?? "", newText ?? ""), [oldText, newText]);
  const rows = useMemo(() => buildRows(changes), [changes]);
  const stats = useMemo(() => {
    let add = 0;
    let del = 0;
    for (const c of changes) {
      const n = c.count ?? 0;
      if (c.added) add += n;
      else if (c.removed) del += n;
    }
    return { add, del };
  }, [changes]);

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2 text-xs">
        <div className="text-slate-500">
          <span className="font-medium text-emerald-700">+{stats.add}</span>{" "}
          <span className="font-medium text-red-700">-{stats.del}</span> lines
        </div>
        <div className="flex gap-1">
          <Button size="sm" variant={mode === "split" ? "primary" : "ghost"} onClick={() => setMode("split")}>
            Side by side
          </Button>
          <Button
            size="sm"
            variant={mode === "unified" ? "primary" : "ghost"}
            onClick={() => setMode("unified")}
          >
            Unified
          </Button>
        </div>
      </div>
      <div className="max-h-[70vh] overflow-auto font-mono text-xs leading-5">
        {mode === "split" ? (
          <table className="w-full table-fixed border-collapse">
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  <td className="w-10 select-none border-r border-slate-100 pr-1 text-right text-slate-400">
                    {row.left?.n ?? ""}
                  </td>
                  <td
                    className={`w-1/2 whitespace-pre-wrap break-words px-2 ${
                      row.left && row.kind !== "same" ? cellBg.del : ""
                    }`}
                  >
                    {row.left?.text ?? ""}
                  </td>
                  <td className="w-10 select-none border-x border-slate-100 pr-1 text-right text-slate-400">
                    {row.right?.n ?? ""}
                  </td>
                  <td
                    className={`w-1/2 whitespace-pre-wrap break-words px-2 ${
                      row.right && row.kind !== "same" ? cellBg.add : ""
                    }`}
                  >
                    {row.right?.text ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div>
            {changes.map((c, i) =>
              c.value
                .replace(/\n$/, "")
                .split("\n")
                .map((line, j) => (
                  <div
                    key={`${i}-${j}`}
                    className={`whitespace-pre-wrap break-words px-3 ${
                      c.added ? cellBg.add : c.removed ? cellBg.del : ""
                    }`}
                  >
                    <span className="mr-2 select-none text-slate-400">
                      {c.added ? "+" : c.removed ? "-" : " "}
                    </span>
                    {line}
                  </div>
                )),
            )}
          </div>
        )}
      </div>
    </div>
  );
}
