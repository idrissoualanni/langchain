// AppSidebar — rail de navigation unique (Assistant / Learning / Profile
// / Settings), conversations et indicateurs de service.
// Le menu Admin est un groupe SÉPARÉ, réservé aux administrateurs.
import { NavLink, useLocation } from 'react-router-dom';
import {
  Bot,
  FileText,
  GraduationCap,
  Moon,
  ScrollText,
  Settings,
  Sun,
  User,
} from 'lucide-react';
import { UserButton } from '@clerk/clerk-react';
import { useHealth } from '@/hooks/useHealth';
import { useCurrentUser } from '@/hooks/useCurrentUser';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from '@/components/ui/sidebar';
import { ThreadList } from '@/components/assistant-ui/elements/thread-list.aui';
import { StatusBadge } from '@/components/layout/StatusBadge';

interface NavItem {
  to: string;
  label: string;
  icon: typeof Bot;
}

const USER_NAV: NavItem[] = [
  { to: '/assistant', label: 'Assistant', icon: Bot },
  { to: '/learning', label: 'Learning', icon: GraduationCap },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/profile', label: 'Profile', icon: User },
];

const SETTINGS_NAV: NavItem = {
  to: '/settings',
  label: 'Paramètres',
  icon: Settings,
};

function NavEntry({ item }: { item: NavItem }) {
  const { pathname } = useLocation();
  const { icon: Icon, label, to } = item;
  const isActive = pathname === to || pathname.startsWith(`${to}/`);

  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={isActive} tooltip={label}>
        <NavLink to={to}>
          <Icon />
          <span>{label}</span>
        </NavLink>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

export function AppSidebar() {
  const { health } = useHealth();
  const { internal, devMode, devLogout, isAdmin } = useCurrentUser();
  const { resolvedTheme, toggle } = useTheme();

  return (
    <Sidebar collapsible="offcanvas">
      {/* Marque — monochrome */}
      <SidebarHeader>
        <div className="flex h-9 items-center gap-2.5 px-1">
          <div className="bg-foreground text-background flex size-7 shrink-0 items-center justify-center rounded-[var(--radius-control)]">
            <Bot size={15} strokeWidth={1.9} />
          </div>
          <div className="min-w-0">
            <div className="text-sidebar-foreground truncate text-[13px] leading-tight font-semibold tracking-tight">
              Agent Lab
            </div>
            <div className="text-muted-foreground truncate font-mono text-[10px] leading-tight">
              control center
            </div>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent className="flex-none gap-0">
        <SidebarGroup>
          <SidebarMenu>
            {USER_NAV.map((item) => (
              <NavEntry key={item.to} item={item} />
            ))}
          </SidebarMenu>
        </SidebarGroup>

        {isAdmin && (
          <SidebarGroup>
            <SidebarGroupLabel className="font-mono tracking-[0.1em] uppercase">
              admin
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <NavEntry
                  item={{ to: '/logs', label: 'Journal', icon: ScrollText }}
                />
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>

      <SidebarSeparator />

      {/* Conversations — ThreadList officiel Assistant UI */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="text-muted-foreground px-4 pt-3 pb-1 font-mono text-[10px] tracking-[0.1em] uppercase">
          conversations
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          <ThreadList />
        </div>
      </div>

      <SidebarFooter className="gap-2 border-t">
        {/* Paramètres — regroupés dans le pied de la sidebar */}
        <SidebarMenu>
          <NavEntry item={SETTINGS_NAV} />
        </SidebarMenu>

        {/* Services — indicateurs discrets */}
        <div className="space-y-1.5 px-1">
          <StatusBadge label="ollama" ok={health ? health.ollama : null} />
          <StatusBadge label="langgraph" ok={health ? health.langgraph : null} />
          <StatusBadge label="sqlite" ok={health ? health.sqlite : null} />
        </div>

        {/* Profil + réglages */}
        <div className="flex items-center gap-2 px-1">
          {devMode ? (
            <button
              onClick={devLogout}
              className="text-muted-foreground hover:text-destructive min-w-0 truncate text-xs font-medium"
              title="Déconnexion (dev)"
            >
              ⏻ {internal?.name ?? 'dev'}
            </button>
          ) : (
            <UserButton afterSignOutUrl="/sign-in" />
          )}
          <span
            className={cn(
              'text-muted-foreground/70 ml-auto shrink-0 font-mono text-[10px]'
            )}
          >
            {internal?.role === 'admin' ? 'admin' : 'user'}
          </span>
          <button
            type="button"
            onClick={toggle}
            aria-label={
              resolvedTheme === 'dark'
                ? 'Passer au thème clair'
                : 'Passer au thème sombre'
            }
            title={resolvedTheme === 'dark' ? 'Thème clair' : 'Thème sombre'}
            className="text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground flex size-6 shrink-0 items-center justify-center rounded-[var(--radius-control)] transition-colors"
          >
            {resolvedTheme === 'dark' ? <Sun size={13} /> : <Moon size={13} />}
          </button>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
