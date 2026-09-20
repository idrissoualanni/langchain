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
import {
  createLocalActivity,
  useActivityStore,
  type ActivityKind,
} from "@/hooks/use-activity-store";

type ActivityItem = {
  label: string;
  icon: LucideIcon;
  instruction: string;
  /** Kind du panneau d'activité (spec §38) créé au déclenchement. */
  kind: ActivityKind;
};

const ACTIVITIES: ActivityItem[] = [
  {
    label: "Quiz flash",
    icon: ListChecks,
    instruction: "Lance un exercice : Quiz flash",
    kind: "quiz",
  },
  {
    label: "Exercice guidé",
    icon: GraduationCap,
    instruction: "Lance un exercice : Exercice guidé",
    kind: "exercise",
  },
  {
    label: "Correction de code",
    icon: Code2,
    instruction: "Lance un exercice : Correction de code",
    kind: "coding",
  },
];

/**
 * Déclencheur d'activité du Composer.
 *
 * Comportement :
 *   - crée une activité "running" dans le store d'activité (spec §38),
 *     active-la et ouvre le panneau latéral ;
 *   - notifie le parent via `onTrigger` (le Composer envoie alors
 *     l'instruction de chat à l'agent) ;
 *   - sans `onTrigger` (usage orphelin hors Composer), affiche
 *     l'instruction en local pour préserver l'ancien comportement.
 *
 * L'activité créée est optimiste : le store assistant-ui la
 * réconciliera avec le véritable événement activity.* du backend.
 */
export function ActivityTrigger({
  onTrigger,
}: {
  onTrigger?: (instruction: string) => void;
}) {
  const [toastText, setToastText] = useState<string | null>(null);

  const handleSelect = (item: ActivityItem) => {
    // Store d'activité : une entrée "running" immédiate + panneau ouvert
    // pour que l'utilisateur voie son activité démarrer (spec §20/§38).
    const activity = createLocalActivity(item.kind, item.label);
    const activityStore = useActivityStore.getState();
    activityStore.upsertActivity(activity);
    activityStore.setActive(activity.id);
    activityStore.togglePanel(true);

    if (onTrigger) {
      onTrigger(item.instruction);
    } else {
      setToastText(item.instruction);
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
        {ACTIVITIES.map((item) => (
          <DropdownMenuItem
            key={item.label}
            onSelect={() => handleSelect(item)}
            className="cursor-pointer"
          >
            <item.icon className="size-4" />
            {item.label}
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
