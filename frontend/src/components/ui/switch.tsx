import * as React from 'react';
import { cn } from '@/lib/utils';

// Simple Switch component – checkbox styled as a toggle.
export const Switch = ({ id, checked = false, onCheckedChange, ...props }: {
  id?: string;
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  className?: string;
}) => {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onCheckedChange?.(e.target.checked);
  };
  return (
    <label className={cn('inline-flex items-center cursor-pointer', props.className)}>
      <input
        type="checkbox"
        id={id}
        checked={checked}
        onChange={handleChange}
        className="sr-only"
        {...props}
      />
      <span className="w-10 h-5 bg-gray-200 rounded-full peer peer-checked:bg-primary transition-colors" />
    </label>
  );
};
