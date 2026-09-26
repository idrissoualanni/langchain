// AppSidebar — rail de navigation unique (Assistant / Learning / Profile
// / Settings), conversations et indicateurs de service.
// Le menu Admin est un groupe SÉPARÉ, réservé aux administrateurs.
import { NavLink, useLocation } from 'react-router-dom';
import {
  BookOpenText,
  Bot,
  Cpu,
  FileText,
  Gauge,
  GraduationCap,
  LayoutDashboard,
  Moon,
  Radar,
  ScrollText,
  Settings,
  Sun,
  User,
  Video,
  Mic,
} from 'lucide-react';
import { NeonUserMenu } from '../auth/NeonUserMenu';
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

const MAIN_NAV: NavItem[] = [
  { to: '/assistant', label: 'Assistant', icon: Bot },
  { to: '/learning', label: 'Learning', icon: GraduationCap },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/memory', label: 'Mémoire', icon: ScrollText },
];

const WORKSPACE_NAV: NavItem[] = [
  { to: '/video', label: 'Vidéo', icon: Video },
  { to: '/voice', label: 'Voix', icon: Mic },
];

const PROFILE_NAV: NavItem = { to: '/profile', label: 'Profil', icon: User };

const SETTINGS_NAV: NavItem = {
  to: '/settings',
  label: 'Paramètres',
  icon: Settings,
};

function NavEntry({ item }: { item: NavItem }) {
  const { pathname } = useLocation();
  const { icon: Icon, label, to } = item;
  const isPrefixRoute = to === '/admin';
  const isActive =
    pathname === to || (!isPrefixRoute && pathname.startsWith(`${to}/`));

  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={isActive} tooltip={label}>
        <NavLink to={to} aria-current={isActive ? 'page' : undefined}>
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

      <SidebarContent className="flex min-h-0 flex-1 gap-0 overflow-hidden">
        <SidebarGroup>
          <SidebarGroupLabel className="font-mono text-[10px] tracking-[0.1em] uppercase">
            principal
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {MAIN_NAV.map((item) => (
                <NavEntry key={item.to} item={item} />
              ))}
              <NavEntry key={PROFILE_NAV.to} item={PROFILE_NAV} />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="font-mono text-[10px] tracking-[0.1em] uppercase">
            workspace
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {WORKSPACE_NAV.map((item) => (
                <NavEntry key={item.to} item={item} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {isAdmin && (
          <SidebarGroup>
            <SidebarGroupLabel className="font-mono tracking-[0.1em] uppercase">
              admin
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <NavEntry
                  item={{ to: '/admin', label: 'Admin', icon: LayoutDashboard }}
                />
                <NavEntry
                  item={{ to: '/admin/models', label: 'Modèles', icon: Cpu }}
                />
                <NavEntry
                  item={{ to: '/admin/knowledge', label: 'Savoir', icon: BookOpenText }}
                />
                <NavEntry
                  item={{ to: '/admin/observability', label: 'Observabilité', icon: Gauge }}
                />
                <NavEntry
                  item={{ to: '/admin/traces', label: 'Traces', icon: Radar }}
                />
                <NavEntry
                  item={{ to: '/logs', label: 'Journal', icon: ScrollText }}
                />
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        <SidebarSeparator className="my-2" />

        {/* Conversations — ThreadList officiel Assistant UI */}
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="text-muted-foreground px-4 pt-2 pb-1 font-mono text-[10px] tracking-[0.1em] uppercase">
            conversations
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            <ThreadList />
          </div>
        </div>
      </SidebarContent>

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
            <NeonUserMenu />
          )}
          <span
            className={cn(
              'text-muted-foreground ml-auto shrink-0 font-mono text-[10px]'
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
