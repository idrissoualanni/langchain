// ChatInput — zone de saisie
// Le placeholder est une invite machine (mono) : ce champ parle à l'agent.
import { useState, type KeyboardEvent } from 'react';
import { Send, Square } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
  running: boolean;
}

export function ChatInput({ onSend, disabled, running }: ChatInputProps) {
  const [text, setText] = useState('');

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="rounded-xl border border-[#26323d] bg-[#111820] p-3">
      <div className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            disabled
              ? '// sélectionnez un utilisateur et un thread'
              : '// écrivez à l\'agent… entrée pour envoyer, maj+entrée pour une nouvelle ligne'
          }
          rows={2}
          className="max-h-40 min-h-[44px] flex-1 resize-none rounded-lg border border-[#26323d] bg-[#18212b] px-3.5 py-2.5 font-mono text-[12.5px] leading-relaxed text-[#f5f7fa] placeholder:text-[#94a3b8]/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6c63ff]/50"
        />
        <button
          onClick={submit}
          disabled={disabled || !text.trim() || running}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[#6c63ff] text-white transition-all hover:bg-[#5b52f0] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
          aria-label={running ? 'Agent en cours' : 'Envoyer'}
        >
          {running ? (
            <Square size={14} className="fill-current" />
          ) : (
            <Send size={15} />
          )}
          {running && <span className="sr-only">en cours</span>}
        </button>
      </div>
    </div>
  );
}
