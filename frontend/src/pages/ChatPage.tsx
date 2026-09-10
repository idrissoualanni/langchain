// ChatPage — page principale : conversation + tools + trace
// La sélection user/thread se fait dans la sidebar ; l'en-tête
// affiche le contexte actif en lecture seule.
import { useEffect, useRef } from 'react';
import { AlertCircle, Bot, MessageSquarePlus } from 'lucide-react';
import { useChat } from '../hooks/useChat';
import { useSelection } from '../hooks/useSelection';
import { useHealth } from '../hooks/useHealth';
import { ChatInput } from '../components/chat/ChatInput';
import { MessageBubble } from '../components/chat/MessageBubble';
import { ToolExecutionCard } from '../components/tools/ToolExecutionCard';
import { ToolStatusPanel } from '../components/tools/ToolStatusPanel';

export function ChatPage({
  onOpenNewUserModal,
  onOpenNewThreadModal,
}: {
  onOpenNewUserModal: () => void;
  onOpenNewThreadModal: () => void;
}) {
  const { currentUser, currentThread } = useSelection();
  const { health } = useHealth();
  const {
    messages,
    toolExecutions,
    status,
    error,
    activity,
    sendMessage,
  } = useChat(currentUser?.user_id ?? null, currentThread?.thread_id ?? null);

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, toolExecutions.length]);

  return (
    <div className="flex h-full flex-col">
      {/* Barre de contexte — sélection dans la sidebar, affichage ici */}
      <div className="flex flex-wrap items-center gap-2.5 border-b border-[#26323d] bg-[#111820]/50 px-6 py-3">
        <h1 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-[#f5f7fa]">
          <Bot size={16} className="text-[#6c63ff]" strokeWidth={1.8} />
          Chat
        </h1>
        <span className="rounded-md bg-[#18212b] px-2 py-1 font-mono text-[10px] text-[#94a3b8]">
          {health?.model ?? '…'}
        </span>

        {/* Contexte actif — lecture seule (sélection dans la sidebar) */}
        <div className="flex items-center gap-2 font-mono text-[11px]">
          {currentUser ? (
            <span className="max-w-[160px] truncate rounded-md bg-[#18212b] px-2 py-1 text-[#f5f7fa]/80">
              {currentUser.name}
            </span>
          ) : (
            <span className="rounded-md bg-[#18212b] px-2 py-1 text-[#94a3b8]/60">
              no user
            </span>
          )}
          <span className="text-[#94a3b8]/40">/</span>
          {currentThread ? (
            <span
              className="max-w-[200px] truncate rounded-md bg-[#18212b] px-2 py-1 text-[#f5f7fa]/80"
              title={currentThread.thread_id}
            >
              {currentThread.name}
            </span>
          ) : (
            <span className="rounded-md bg-[#18212b] px-2 py-1 text-[#94a3b8]/60">
              no thread
            </span>
          )}
        </div>

        <button
          onClick={onOpenNewThreadModal}
          disabled={!currentUser}
          className="flex items-center gap-1.5 rounded-lg border border-[#26323d] bg-[#18212b] px-3 py-1.5 text-[13px] font-medium text-[#f5f7fa] transition-colors hover:border-[#6c63ff]/50 hover:text-[#6c63ff] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <MessageSquarePlus size={13} />
          Thread
        </button>

        <div className="ml-auto flex items-center gap-2">
          <span
            className={`flex items-center gap-1.5 rounded-md px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider ${
              status === 'running'
                ? 'bg-[#6c63ff]/15 text-[#6c63ff]'
                : 'bg-[#22c55e]/10 text-[#22c55e]'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                status === 'running'
                  ? 'bg-[#6c63ff] pulse-dot'
                  : 'bg-[#22c55e]'
              }`}
            />
            {status === 'running' ? 'running' : 'online'}
          </span>
        </div>
      </div>

      {/* Corps */}
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col p-6">
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-2">
            {!currentThread && (
              <div className="flex h-full items-center justify-center">
                <div className="max-w-sm text-center">
                  <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-[#6c63ff] to-[#8b83ff]">
                    <Bot size={26} className="text-white" />
                  </div>
                  <div className="mb-2 text-[15px] font-semibold text-[#f5f7fa]">
                    Prêt à discuter avec l'agent
                  </div>
                  <p className="mb-5 text-[13px] leading-relaxed text-[#94a3b8]">
                    Sélectionnez un utilisateur et un thread existants,
                    ou créez-en un en deux clics.
                  </p>
                  <div className="flex justify-center gap-2.5">
                    <button
                      onClick={onOpenNewUserModal}
                      className="rounded-lg bg-[#6c63ff] px-4 py-2 text-[13px] font-medium text-white transition hover:bg-[#5b52f0]"
                    >
                      Créer un utilisateur
                    </button>
                    {currentUser && (
                      <button
                        onClick={onOpenNewThreadModal}
                        className="rounded-lg border border-[#26323d] bg-[#18212b] px-4 py-2 text-[13px] font-medium text-[#f5f7fa] transition hover:border-[#6c63ff]/50 hover:text-[#6c63ff]"
                      >
                        Créer un thread
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}

            {currentThread && messages.length === 0 && status !== 'running' && (
              <div className="flex h-full items-center justify-center font-mono text-[12px] text-[#94a3b8]/60">
                thread vide — écrivez le premier message
              </div>
            )}

            {currentThread &&
              messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)}

            {currentThread &&
              toolExecutions.map((exec) => (
                <div key={exec.id} className="pl-11">
                  <ToolExecutionCard execution={exec} />
                </div>
              ))}

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-[#ef4444]/30 bg-[#ef4444]/5 p-3 pl-11">
                <AlertCircle size={15} className="mt-0.5 shrink-0 text-[#ef4444]" />
                <span className="text-[13px] text-[#ef4444]">{error}</span>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          <div className="mt-4">
            <ChatInput
              onSend={sendMessage}
              disabled={!currentUser || !currentThread || status === 'running'}
              running={status === 'running'}
            />
          </div>
        </div>

        <div className="hidden w-[300px] shrink-0 border-l border-[#26323d] bg-[#0b0f14] p-4 xl:block">
          <ToolStatusPanel
            toolExecutions={toolExecutions}
            activity={activity}
            running={status === 'running'}
          />
        </div>
      </div>
    </div>
  );
}
