// CommandPalette — ⌘K quick jump (§29 D3) — cmdk + Dialog
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Command } from 'cmdk';
import { Bot, FileText, GraduationCap, Database, Settings, Video, Mic, LayoutDashboard } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';

const COMMANDS = [
  { label: 'Assistant', to: '/assistant', icon: Bot },
  { label: 'Learning', to: '/learning', icon: GraduationCap },
  { label: 'Documents', to: '/documents', icon: FileText },
  { label: 'Mémoire', to: '/memory', icon: Database },
  { label: 'Vidéo', to: '/video', icon: Video },
  { label: 'Voix', to: '/voice', icon: Mic },
  { label: 'Paramètres', to: '/settings', icon: Settings },
  { label: 'Admin', to: '/admin', icon: LayoutDashboard },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', down);
    return () => window.removeEventListener('keydown', down);
  }, []);

  const run = (to: string) => {
    setOpen(false);
    navigate(to);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen} title="Navigation rapide" className="max-w-lg p-0">
      <Command className="overflow-hidden rounded-xl">
        <Command.Input
          placeholder="Aller à… (assistant, learning, documents…)"
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm outline-none placeholder:text-muted-foreground"
        />
        <Command.List className="max-h-80 overflow-y-auto p-2">
          <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">
            Aucun résultat.
          </Command.Empty>
          <Command.Group heading="Pages" className="px-2 py-1 text-[11px] font-mono uppercase tracking-wide text-muted-foreground">
            {COMMANDS.map(({ label, to, icon: Icon }) => (
              <Command.Item
                key={to}
                value={label}
                onSelect={() => run(to)}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
              >
                <Icon size={14} className="text-muted-foreground" />
                {label}
              </Command.Item>
            ))}
          </Command.Group>
        </Command.List>
        <div className="border-t border-border px-3 py-2 text-right font-mono text-[10px] text-muted-foreground">
          ⌘K pour ouvrir · ESC pour fermer
        </div>
      </Command>
    </Dialog>
  );
}
