// MessageBubble — bulle user / assistant
// Sémantique typographique : l'utilisateur parle en Sans (voix humaine),
// l'assistant répond en Sans aussi (c'est une conversation), mais le
// contenu agent est marqué par la voix bot en accent.
//
// V6.7 : si le message assistant porte une AgentResponse, le
// ResponseRenderer prend le relais (cartes riches typées par
// response.type — JAMAIS de parsing de texte §18). Sinon
// (historique ancien), affichage texte inchangé.
import { motion } from 'framer-motion';
import { Bot, User } from 'lucide-react';
import type { ChatMessage } from '../../types/agent';
import { ResponseRenderer } from '../agent/ResponseRenderer';

export function MessageBubble({
  message,
  threadId,
  userId,
  onAction,
  onOption,
}: {
  message: ChatMessage;
  threadId?: string | null;
  userId?: string | null;
  onAction?: (type: string) => void;
  onOption?: (option: string) => void;
}) {
  const isUser = message.role === 'user';
  const hasStructured =
    !isUser && message.agentResponse != null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
          isUser
            ? 'border border-[#26323d] bg-[#18212b] text-[#94a3b8]'
            : 'bg-gradient-to-br from-[#6c63ff] to-[#8b83ff] text-white'
        }`}
      >
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>

      {hasStructured ? (
        <div className="min-w-0 max-w-[85%]">
          <ResponseRenderer
            response={message.agentResponse!}
            threadId={threadId}
            userId={userId}
            onAction={onAction}
            onOption={onOption}
          />
        </div>
      ) : (
        <div
          className={`max-w-[75%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? 'rounded-tr-sm bg-[#6c63ff] text-white'
              : 'rounded-tl-sm border border-[#26323d] bg-[#111820] text-[#f5f7fa]'
          }`}
        >
          <div className="whitespace-pre-wrap break-words">
            {message.content}
          </div>
        </div>
      )}
    </motion.div>
  );
}
