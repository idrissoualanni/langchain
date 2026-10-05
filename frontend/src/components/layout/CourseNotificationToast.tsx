import { useEffect, useState } from "react";
import { Bell, X, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useActivityStore } from "@/hooks/use-activity-store";
import { cn } from "@/lib/utils";

export function CourseNotificationToast() {
  const { notifications, markNotificationRead, clearNotifications } = useActivityStore();
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (notifications.length > 0) {
      setIsVisible(true);
    }
  }, [notifications]);

  if (!isVisible || notifications.length === 0) return null;

  const latest = notifications[0];

  return (
    <div className="fixed bottom-4 right-4 z-50 w-full max-w-sm animate-in slide-in-from-bottom-4 fade-in">
      <div className="relative overflow-hidden rounded-lg border bg-background p-4 shadow-lg">
        <div className="flex items-start gap-3">
          <div className="rounded-full bg-primary/10 p-2 text-primary">
            <Bell className="h-4 w-4" />
          </div>
          <div className="flex-1 space-y-1">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium leading-none">
                Nouveau contenu disponible
              </p>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsVisible(false)}
                className="h-6 w-6 p-0"
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {latest.message}
            </p>
            <div className="flex justify-end pt-2">
              <Button
                size="sm"
                className="h-7 px-2 text-[11px]"
                onClick={() => {
                  markNotificationRead(latest.id);
                  setIsVisible(false);
                }}
              >
                <CheckCircle2 className="mr-1 h-3 w-3" /> Marquer comme lu
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
