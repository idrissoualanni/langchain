import * as React from "react";
import { cn } from "@/lib/utils";

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Completion percentage (0-100). */
  value?: number;
  /** Maximum value, default 100. */
  max?: number;
}

export const Progress = ({
  className,
  value = 0,
  max = 100,
  ...props
}: ProgressProps) => {
  const percentage = Math.min(Math.max(value / max, 0), 1) * 100;
  return (
    <div
      className={cn(
        "relative w-full overflow-hidden rounded-full bg-primary/10",
        className
      )}
      {...props}
    >
      <div
        className="h-full bg-primary transition-all"
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
};
