import { WikiTree } from "@/components/WikiTree";

export default function WikiLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <WikiTree />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
