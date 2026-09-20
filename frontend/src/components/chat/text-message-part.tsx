"use client";

import type { TextMessagePartProps } from "@assistant-ui/react";
import { MarkdownText } from "@/components/assistant-ui/elements/markdown-text";

export function TextMessagePart(props: TextMessagePartProps) {
  return <MarkdownText {...props} />;
}