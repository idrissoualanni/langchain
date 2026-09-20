import * as React from 'react';
import { cn } from '@/lib/utils';

// Minimal Select component set – inspired by shadcn/ui but simplified.
// Provides Select, SelectTrigger, SelectValue, SelectContent, SelectItem.

export const Select = ({ children, onValueChange, value, ...props }: {
  children: React.ReactNode;
  onValueChange?: (value: string) => void;
  value?: string;
  className?: string;
}) => {
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onValueChange?.(e.target.value);
  };
  return (
    <select
      value={value}
      onChange={handleChange}
      className={cn('rounded-md border border-input bg-background px-3 py-2 text-sm', props.className)}
      {...props}
    >
      {children}
    </select>
  );
};

export const SelectTrigger = Select;

export const SelectValue = ({ placeholder }: { placeholder?: string }) => {
  return placeholder ? <span className="text-muted-foreground">{placeholder}</span> : null;
};

export const SelectContent = ({ children }: { children: React.ReactNode }) => {
  return <>{children}</>;
};

export const SelectItem = ({ value, children }: { value: string; children: React.ReactNode }) => {
  return <option value={value}>{children}</option>;
};
