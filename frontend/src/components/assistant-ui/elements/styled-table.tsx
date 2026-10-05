"use client";

import React, { memo } from "react";
import { cn } from "@/lib/utils";

interface StyledTableProps {
  data: any[];
  columns: {
    header: string;
    accessor: string;
    className?: string;
  }[];
  className?: string;
}

export const StyledTable = memo(({ data, columns, className }: StyledTableProps) => {
  if (!data || data.length === 0) {
    return (
      <div className="py-4 text-center text-sm text-muted-foreground italic">
        Aucune donnée disponible
      </div>
    );
  }

  return (
    <div className={cn("my-4 overflow-hidden rounded-xl border border-border", className)}>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-muted/50 border-b border-border">
              {columns.map((col, i) => (
                <th
                  key={i}
                  className={cn(
                    "px-4 py-3 text-start font-semibold text-foreground/80",
                    col.className
                  )}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className="transition-colors hover:bg-muted/30"
              >
                {columns.map((col, colIndex) => (
                  <td
                    key={colIndex}
                    className={cn(
                      "px-4 py-3 text-foreground/70",
                      col.className
                    )}
                  >
                    {row[col.accessor]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});

StyledTable.displayName = "StyledTable";
