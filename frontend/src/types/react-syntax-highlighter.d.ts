declare module "react-syntax-highlighter" {
  import type { ComponentType, CSSProperties } from "react";

  export interface SyntaxHighlighterProps {
    language?: string;
    style?: unknown;
    children?: string | string[];
    customStyle?: CSSProperties;
    className?: string;
    PreTag?: ComponentType<Record<string, unknown>>;
    CodeTag?: ComponentType<Record<string, unknown>>;
    codeTagProps?: Record<string, unknown>;
    showLineNumbers?: boolean;
    [key: string]: unknown;
  }

  interface PrismAsyncLightComponent extends ComponentType<SyntaxHighlighterProps> {
    registerLanguage(name: string, language: unknown): void;
  }

  const PrismAsyncLight: PrismAsyncLightComponent;
  export { PrismAsyncLight };
}

declare module "react-syntax-highlighter/dist/esm/languages/prism/*" {
  const language: unknown;
  export default language;
}

declare module "react-syntax-highlighter/dist/cjs/styles/prism" {
  const coldarkCold: Record<string, unknown>;
  const coldarkDark: Record<string, unknown>;
  export { coldarkCold, coldarkDark };
}

declare module "react-syntax-highlighter/dist/cjs/styles/prism/*" {
  const style: Record<string, unknown>;
  export { style };
}