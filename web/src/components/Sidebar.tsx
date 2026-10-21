"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV: { href: string; label: string; hint: string }[] = [
  { href: "/documents", label: "Documents", hint: "Upload and track ingest" },
  { href: "/search", label: "Search", hint: "Hybrid retrieval" },
  { href: "/chat", label: "Chat", hint: "Cited answers" },
  { href: "/wiki", label: "Wiki", hint: "Engineering knowledge" },
  { href: "/review", label: "Review", hint: "Wiki proposals" },
  { href: "/compliance", label: "Compliance", hint: "Requirement checks" },
  { href: "/specs", label: "Specs", hint: "Author and check" },
];

export function Sidebar() {
  const pathname = usePathname() ?? "";
  return (
    <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-4">
        <Link href="/documents" className="block">
          <div className="text-base font-semibold tracking-tight text-slate-900">
            Engineering Brain
          </div>
          <div className="text-xs text-slate-500">Document control and review</div>
        </Link>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`mb-0.5 block rounded-md px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-slate-900 text-white"
                  : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              <div className="font-medium">{item.label}</div>
              <div className={`text-xs ${active ? "text-slate-300" : "text-slate-400"}`}>
                {item.hint}
              </div>
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-slate-200 px-4 py-3 text-xs text-slate-400">
        dev mode &middot; no auth
      </div>
    </aside>
  );
}
