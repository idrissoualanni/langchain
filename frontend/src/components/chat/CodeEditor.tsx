// CodeEditor V5.2 — pratique du code Python avec exécution réelle
//
// Le tuteur N'ÉCRIT JAMAIS le code à la place de l'étudiant (§31) :
// cet éditeur permet à l'ÉTUDIANT d'écrire et d'exécuter SON code
// dans la sandbox backend isolée (POST /api/threads/{id}/run-code,
// §24-§27). Aucune simulation : chaque exécution est réelle, les
// erreurs 400 (scan statique) et 403 (isolation utilisateur) du
// backend sont affichées telles quelles.
//
// UX clavier : Tab insère 2 espaces (convention pédagogique simple),
// Maj+Tab retire une indentation.
import { useRef, useState, type KeyboardEvent } from 'react';
import {
  Eraser,
  Loader2,
  Play,
  ShieldAlert,
  Terminal,
} from 'lucide-react';
import type { CodeRunResult } from '../../types/activity';
import { runCode } from '../../api/activity';
import { ApiError } from '../../api/base';
import { TestResultPanel } from './TestResultPanel';

interface CodeEditorProps {
  userId: string | null;
  threadId: string | null;
}

const DEFAULT_CODE = '# Écrivez votre code Python ici\n# puis cliquez sur Exécuter pour le lancer dans la sandbox.\n';

export function CodeEditor({ userId, threadId }: CodeEditorProps) {
  const [code, setCode] = useState<string>(DEFAULT_CODE);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CodeRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);

  const handleScroll = () => {
    if (gutterRef.current && textareaRef.current) {
      gutterRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  };

  const canRun =
    Boolean(userId) && Boolean(threadId) && !running && code.trim().length > 0;

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = e.currentTarget;
      const { selectionStart: start, selectionEnd: end } = ta;
      if (e.shiftKey) {
        // Maj+Tab : retire une indentation (2 espaces) si présente
        if (code.slice(start - 2, start) === '  ') {
          const next = code.slice(0, start - 2) + code.slice(end);
          setCode(next);
          requestAnimationFrame(() => ta.setSelectionRange(start - 2, start - 2));
        }
      } else {
        // Tab : insère 2 espaces
        const next = code.slice(0, start) + '  ' + code.slice(end);
        setCode(next);
        requestAnimationFrame(() => ta.setSelectionRange(start + 2, start + 2));
      }
    }
  };

  const handleRun = async () => {
    if (!userId || !threadId || running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await runCode(threadId, userId, code);
      setResult(res);
    } catch (exc) {
      if (exc instanceof ApiError) {
        // Messages réels du backend : 400 (code interdit par le scan
        // statique), 403 (thread d'un autre utilisateur), 404…
        if (exc.status === 403) {
          setError(
            'Ce thread n\'appartient pas à cet utilisateur — exécution refusée (isolation).'
          );
        } else {
          setError(exc.message);
        }
      } else {
        setError(exc instanceof Error ? exc.message : String(exc));
      }
    } finally {
      setRunning(false);
    }
  };

  const handleClear = () => {
    setCode('');
    setResult(null);
    setError(null);
  };

  // ----- État vide : pas de thread sélectionné (le run-code EST thread-scoped) -----
  if (!threadId) {
    return (
      <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[#26323d] p-6 text-center">
        <Terminal size={24} className="text-[#94a3b8]/30" />
        <p className="font-mono text-[11px] text-[#94a3b8]">
          Sélectionnez un thread pour pratiquer le code.
        </p>
        <p className="font-mono text-[10px] text-[#94a3b8]/50">
          l'exécution est attachée au thread courant (sandbox isolée)
        </p>
      </div>
    );
  }

  const lineCount = code.split('\n').length;

  return (
    <div className="flex flex-col gap-3">
      {/* Barre d'outils : badge langage + boutons */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 rounded-md border border-[#6c63ff]/30 bg-[#6c63ff]/15 px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-wide text-[#6c63ff]">
          <Terminal size={11} strokeWidth={2} />
          python
        </span>
        <span className="font-mono text-[10px] text-[#94a3b8]/50">
          {lineCount} ligne{lineCount > 1 ? 's' : ''}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={handleClear}
            disabled={running || (code.length === 0 && !result && !error)}
            className="flex items-center gap-1.5 rounded-lg border border-[#26323d] bg-[#18212b] px-2.5 py-1.5 font-mono text-[11px] text-[#94a3b8] transition-colors hover:text-[#f5f7fa] disabled:opacity-40"
            title="Effacer l'éditeur et les résultats"
          >
            <Eraser size={12} />
            Effacer
          </button>
          <button
            type="button"
            onClick={() => void handleRun()}
            disabled={!canRun}
            className="flex items-center gap-1.5 rounded-lg bg-[#6c63ff] px-3 py-1.5 font-mono text-[11px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            title="Exécuter dans la sandbox isolée (10s max)"
          >
            {running ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Play size={12} strokeWidth={2.5} fill="currentColor" />
            )}
            {running ? 'exécution…' : 'Exécuter'}
          </button>
        </div>
      </div>

      {/* Éditeur mono avec numéros de ligne */}
      <div className="flex overflow-hidden rounded-lg border border-[#26323d] bg-[#0b0f14] focus-within:border-[#6c63ff]/50">
        <div
          ref={gutterRef}
          aria-hidden="true"
          className="max-h-[420px] select-none overflow-hidden border-r border-[#26323d]/60 bg-[#0d1117] px-2 py-2.5 text-right font-mono text-[11px] leading-relaxed text-[#94a3b8]/40"
        >
          {Array.from({ length: lineCount }, (_, i) => (
            <div key={i}>{i + 1}</div>
          ))}
        </div>
        <textarea
          ref={textareaRef}
          onScroll={handleScroll}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={running}
          spellCheck={false}
          placeholder="# votre code python…"
          rows={12}
          className="max-h-[420px] min-h-[200px] w-full resize-none overflow-auto bg-transparent px-3 py-2.5 font-mono text-[11px] leading-relaxed text-[#f5f7fa] placeholder:text-[#94a3b8]/40 focus:outline-none disabled:opacity-60"
        />
      </div>

      {/* Erreur API (400 code interdit, 403 isolation, réseau…) */}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-[#ef4444]">
          <ShieldAlert size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Résultat réel de la sandbox */}
      {result && <TestResultPanel result={result} />}
    </div>
  );
}
