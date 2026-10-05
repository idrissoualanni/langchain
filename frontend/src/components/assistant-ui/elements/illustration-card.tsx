"use client";

import React, { memo } from "react";
import { cn } from "@/lib/utils";
import { info } from "lucide-react";

interface IllustrationCardProps {
  id: string;
  type: "diagram" | "table" | "image";
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export const IllustrationCard = memo(({
  id,
  type,
  title,
  children,
  className
}: IllustrationCardProps) => {
  return (
    <div
      key={id}
      className={cn(
        "my-6 overflow-hidden rounded-2xl border border-border bg-card shadow-sm",
        className
      )}
    >
      {title && (
        <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-4 py-2 text-xs font-medium text-muted-foreground">
          <info className="h-3.5 w-3.5" />
          <span>{title}</span>
        </div>
      )}
      <div className="p-4">
        {children}
      </div>
    </div>
  );
});

IllustrationCard.displayName = "IllustrationCard";
