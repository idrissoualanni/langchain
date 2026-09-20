import * as React from 'react';
import { cn } from '@/lib/utils';

// Simple ScrollArea – a div with overflow-y auto and optional className.
export const ScrollArea = ({ className, children, ...props }: {
  className?: string;
  children: React.ReactNode;
}) => (
  <div
    className={cn('overflow-y-auto', className)}
    {...props}
  >
    {children}
  </div>
);
