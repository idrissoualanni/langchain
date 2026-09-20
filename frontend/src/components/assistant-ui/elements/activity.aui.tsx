"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Zap,
  GraduationCap,
  Code2,
  ListChecks,
  type LucideIcon,
} from "lucide-react";

type ActivityItem = {
  label: string;
  icon: LucideIcon;
  instruction: string;
};

const ACTIVITIES: ActivityItem[] = [
  {
    label: "Quiz flash",
    icon: ListChecks,
    instruction: "Lance un exercice : Quiz flash",
  },
  {
    label: "Exercice guidé",
    icon: GraduationCap,
    instruction: "Lance un exercice : Exercice guidé",
  },
  {
    label: "Correction de code",
    icon: Code2,
    instruction: "Lance un exercice : Correction de code",
  },
];

export function ActivityTrigger({
  onTrigger,
}: {
  onTrigger?: (instruction: string) => void;
}) {
  const [toastText, setToastText] = useState<string | null>(null);

  const handleSelect = (instruction: string) => {
    if (onTrigger) {
      onTrigger(instruction);
    } else {
      setToastText(instruction);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="text-muted-foreground hover:text-foreground h-8 gap-1 rounded-lg text-xs"
        >
          <Zap className="size-3.5" />
          Activité
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56 p-1">
        {ACTIVITIES.map(({ label, icon: Icon, instruction }) => (
          <DropdownMenuItem
            key={label}
            onSelect={() => handleSelect(instruction)}
            className="cursor-pointer"
          >
            <Icon className="size-4" />
            {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
      {!onTrigger && toastText && (
        <p className="text-muted-foreground mt-1 text-xs">{toastText}</p>
      )}
    </DropdownMenu>
  );
}

ActivityTrigger.displayName = "ActivityTrigger";