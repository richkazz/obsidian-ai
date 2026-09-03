"use client"

import { usePathname } from "next/navigation"
import { useSession, signOut } from "next-auth/react"
import { useTheme } from "next-themes"
import Link from "next/link"
import { motion } from "motion/react"
import {
  Home,
  MessageSquare,
  History,
  Settings,
  Shield,
  LogOut,
  ChevronDown,
  BookOpen,
  FlaskConical,
  BarChart2,
  MessageCircle,
  Key,
  BookMarked,
  Sparkles,
  Code2,
  Moon,
  Sun,
} from "lucide-react"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import { Routes } from "@/config/routes"
import { springTransition } from "@/lib/motion"
import Logo from "./ui/logo"

type NavItem = { label: string; icon: React.ElementType; path: string }

const mainItems: NavItem[] = [
  { label: "Home",         icon: Home,          path: Routes.DASHBOARD },
  { label: "Chat",         icon: MessageSquare, path: Routes.PLAYGROUND },
  { label: "Sessions",     icon: History,       path: Routes.SESSIONS },
]

const vaultItems: NavItem[] = [
  { label: "Knowledge",    icon: BookOpen,      path: Routes.KNOWLEDGE },
  { label: "Prompts",      icon: BookMarked,    path: Routes.PROMPTS },
  { label: "Skills",       icon: Sparkles,      path: Routes.SKILLS },
  { label: "Secrets",      icon: Key,           path: Routes.SECRETS },
]

const toolItems: NavItem[] = [
  { label: "Evals",        icon: FlaskConical,  path: Routes.EVALS },
  { label: "Observability",icon: BarChart2,     path: Routes.OBSERVABILITY },
  { label: "Channels",     icon: MessageCircle, path: Routes.CHANNELS },
  { label: "Developer",    icon: Code2,         path: Routes.DEVELOPER },
]

const systemItems: NavItem[] = [
  { label: "Settings",     icon: Settings,      path: Routes.SETTINGS },
]

const adminItems: NavItem[] = [
  { label: "Admin",        icon: Shield,        path: Routes.ADMIN_PANEL },
]

const groups: { label: string; items: NavItem[] }[] = [
  { label: "",        items: mainItems },
  { label: "Vaults",  items: vaultItems },
  { label: "Tools",   items: toolItems },
  { label: "System",  items: systemItems },
]

export function AppSidebar() {
  const pathname = usePathname()
  const { data: session } = useSession()
  const userRole = (session?.user as { role?: string })?.role
  const { resolvedTheme, setTheme } = useTheme()

  const isActive = (item: NavItem) =>
    pathname === item.path ||
    (item.path === Routes.PLAYGROUND && pathname.startsWith("/playground"))

  const renderItem = (item: NavItem) => (
    <Link
      key={item.path}
      href={item.path}
      className={cn(
        "relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
        isActive(item)
          ? "text-sidebar-accent-foreground font-medium"
          : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
      )}
    >
      {isActive(item) && (
        <motion.div
          layoutId="sidebar-active-pill"
          className="absolute inset-0 bg-sidebar-accent rounded-lg"
          transition={springTransition}
        />
      )}
      <item.icon className="relative h-4 w-4 shrink-0" />
      <span className="relative">{item.label}</span>
    </Link>
  )

  return (
    <div className="flex flex-col h-full w-72 bg-sidebar text-sidebar-foreground border-r border-sidebar-border shrink-0">
      {/* Logo */}
      <div className="flex items-center h-14 px-5 border-b border-sidebar-border">
        <Logo className="h-5" />
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        {groups.map((group, gi) => (
          <div key={gi} className={gi > 0 ? "mt-5" : ""}>
            {group.label && (
              <p className="px-3 mb-1.5 text-[11px] font-semibold uppercase tracking-widest text-sidebar-foreground/60">
                {group.label}
              </p>
            )}
            <div className="space-y-1">
              {group.items.map(renderItem)}
              {/* Inject admin item after System group */}
              {group.label === "System" && userRole === "admin" && adminItems.map(renderItem)}
            </div>
          </div>
        ))}
      </nav>

      {/* User section */}
      <div className="px-3 py-3 border-t border-sidebar-border">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-2 w-full px-2 py-1.5 rounded-md hover:bg-sidebar-accent/50 transition-colors">
              <Avatar className="h-7 w-7">
                <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">
                  {session?.user?.name?.[0]?.toUpperCase() || session?.user?.email?.[0]?.toUpperCase() || "U"}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0 text-left">
                <p className="text-xs font-semibold uppercase truncate">
                  {(session?.user?.name || session?.user?.email || "User").charAt(0).toUpperCase() +
                    (session?.user?.name || session?.user?.email || "User").slice(1)}
                </p>
              </div>
              <ChevronDown className="h-3 w-3 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-48">
            <div className="px-2 py-1.5">
              <p className="text-xs text-muted-foreground">Signed in as</p>
              <p className="text-sm font-medium truncate">{session?.user?.email}</p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer"
              onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            >
              {resolvedTheme === "dark" ? (
                <Sun className="h-4 w-4 mr-2" />
              ) : (
                <Moon className="h-4 w-4 mr-2" />
              )}
              {resolvedTheme === "dark" ? "Light mode" : "Dark mode"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-destructive cursor-pointer"
              onClick={() => signOut({ callbackUrl: "/login" })}
            >
              <LogOut className="h-4 w-4 mr-2" />
              Sign Out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}
