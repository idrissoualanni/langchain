// TextResponse V6.7 — réponse textuelle standard (type=text).
import { motion } from 'framer-motion';

export function TextResponse({ message }: { message: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[#f5f7fa]/90"
    >
      {message}
    </motion.div>
  );
}
