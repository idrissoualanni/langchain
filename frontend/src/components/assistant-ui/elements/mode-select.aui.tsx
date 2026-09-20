"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Bot,
  BookOpen,
  ChevronDown,
  Cpu,
  Search,
  Video,
} from "lucide-react";

const MODES = [
  { label: "Assistant Général", icon: Bot },
  { label: "Recherche & Synthèse", icon: Search },
  { label: "Vidéo & Multi-modal", icon: Video },
  { label: "Apprentissage actif", icon: BookOpen },
  { label: "Modèles & Tools (MCP)", icon: Cpu },
];

export function ModeSelectButton({
  onChange,
}: {
  onChange?: (mode: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          className="text-muted-foreground hover:text-foreground h-8 gap-1 rounded-lg text-xs"
        >
          Mode <ChevronDown className="size-3" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-1">
        {MODES.map(({ label, icon: Icon }) => (
          <button
            key={label}
            onClick={() => {
              onChange?.(label);
              setOpen(false);
            }}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
          >
            <Icon className="size-4" />
            {label}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}

ModeSelectButton.displayName = "ModeSelectButton";