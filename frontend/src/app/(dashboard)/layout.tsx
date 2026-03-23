import Link from "next/link";

const navItems = [
  { href: "/upload", label: "Upload", icon: "↑" },
  { href: "/datasets", label: "Datasets", icon: "◫" },
  { href: "/chat", label: "AI Chat", icon: "◉" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-h-screen">
      <aside className="w-56 shrink-0 border-r bg-card p-4 flex flex-col gap-1">
        <Link
          href="/upload"
          className="text-lg font-semibold tracking-tight px-3 py-2 mb-4"
        >
          Excel Consultant
        </Link>
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="flex-1 overflow-auto bg-background p-6">
        {children}
      </main>
    </div>
  );
}
