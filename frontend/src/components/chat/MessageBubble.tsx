// MessageBubble — bulle user / assistant
// Sémantique typographique : l'utilisateur parle en Sans (voix humaine),
// l'assistant répond en Sans aussi (c'est une conversation), mais le
// contenu agent est marqué par la voix bot en accent.
import { motion } from 'framer-motion';
import { Bot, User } from 'lucide-react';
import type { ChatMessage } from '../../types/agent';

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

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
    </motion.div>
  );
}
