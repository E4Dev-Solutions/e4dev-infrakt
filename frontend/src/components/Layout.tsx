import { NavLink, Outlet } from "react-router-dom";
import {
  BarChart3,
  Server,
  Box,
  Database,
  Globe,
  Zap,
  LogOut,
  Settings as SettingsIcon,
} from "lucide-react";

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  {
    to: "/",
    label: "Dashboard",
    icon: <BarChart3 size={18} aria-hidden="true" />,
  },
  {
    to: "/servers",
    label: "Servers",
    icon: <Server size={18} aria-hidden="true" />,
  },
  {
    to: "/apps",
    label: "Apps",
    icon: <Box size={18} aria-hidden="true" />,
  },
  {
    to: "/databases",
    label: "Databases",
    icon: <Database size={18} aria-hidden="true" />,
  },
  {
    to: "/proxy",
    label: "Proxy",
    icon: <Globe size={18} aria-hidden="true" />,
  },
  {
    to: "/settings",
    label: "Settings",
    icon: <SettingsIcon size={18} aria-hidden="true" />,
  },
];

interface LayoutProps {
  onLogout?: () => void;
}

export default function Layout({ onLogout }: LayoutProps) {
  return (
    <div className="flex h-full min-h-screen bg-zinc-950">
      {/* Sidebar */}
      <aside
        className="flex w-60 shrink-0 flex-col border-r border-zinc-800/80 bg-zinc-900/50"
        aria-label="Main navigation"
      >
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 border-b border-zinc-800/80 px-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 shadow-lg shadow-orange-500/15">
            <Zap size={17} className="text-white" aria-hidden="true" />
          </div>
          <div>
            <span className="text-lg font-bold tracking-tight text-zinc-100">
              infrakT
            </span>
            <span className="ml-1.5 font-mono text-[10px] text-zinc-600">
              v0.1
            </span>
          </div>
        </div>

        {/* Nav links */}
        <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Sidebar navigation">
          <ul className="space-y-0.5" role="list">
            {navItems.map(({ to, label, icon }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    [
                      "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
                      isActive
                        ? "bg-orange-500/10 text-orange-400 shadow-sm shadow-orange-500/5"
                        : "text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-200",
                    ].join(" ")
                  }
                >
                  {icon}
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* Footer */}
        <div className="border-t border-zinc-800/80 px-5 py-4 flex items-center justify-between">
          <p className="font-mono text-[11px] text-zinc-600">infrakT</p>
          {onLogout && (
            <button
              onClick={onLogout}
              className="rounded-md p-1.5 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-400 transition-colors"
              title="Sign out"
            >
              <LogOut size={14} />
            </button>
          )}
        </div>
      </aside>

      {/* Main content */}
      <div className="flex min-w-0 flex-1 flex-col bg-zinc-950">
        <main className="flex-1 overflow-y-auto p-8" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
