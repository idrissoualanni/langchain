// DropZone — drag & drop documents (§13) : Uploading/Processing/Ready/Failed
import { useRef, useState, type DragEvent } from 'react';
import { Upload, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DropZoneProps {
  onFiles: (files: FileList) => void;
  accept?: string;
  maxBytes?: number;
  disabled?: boolean;
  className?: string;
}

export function DropZone({ onFiles, accept, maxBytes, disabled, className }: DropZoneProps) {
  const [dragOver, setDragOver] = useState(false);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    if (!disabled) setDragOver(true);
  };
  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };
  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled || !e.dataTransfer.files.length) return;
    onFiles(e.dataTransfer.files);
  };

  const inputRef = useRef<HTMLInputElement>(null);
  const openPicker = () => {
    if (!disabled) inputRef.current?.click();
  };

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      onClick={openPicker}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openPicker();
        }
      }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-colors',
        dragOver ? 'border-live bg-live/5' : 'border-border bg-muted/20 hover:bg-muted/40',
        disabled && 'opacity-50 pointer-events-none',
        className
      )}
    >
      <div className={cn('rounded-full p-3', dragOver ? 'bg-live text-white' : 'bg-muted text-muted-foreground')}>
        {dragOver ? <Upload size={18} /> : <FileText size={18} />}
      </div>
      <p className="mt-3 text-sm font-medium text-foreground">
        Glisse tes fichiers ici
      </p>
      <p className="mt-1 font-mono text-[11px] text-muted-foreground">
        ou clique pour parcourir · txt, md, pdf (max {maxBytes ? `${(maxBytes / 1_000_000).toFixed(0)} Mo` : '2 Mo'})
      </p>
      {accept && <p className="mt-1 font-mono text-[10px] text-muted-foreground">{accept}</p>}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple
        aria-label="Choisir des fichiers à déposer"
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) onFiles(e.target.files);
          e.target.value = '';
        }}
      />
    </div>
  );
}
