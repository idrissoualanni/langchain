export interface ModelCapabilities {
  supports_tools?: boolean;
  supports_structured_output?: boolean;
  supports_vision?: boolean;
  supports_audio?: boolean;
}

export interface ModelConfig {
  id: string;
  display_name?: string;
  provider: string;
  model_name: string;
  gateway_model?: string;
  enabled: boolean;
  context_window?: number | null;
  max_output_tokens?: number | null;
  capabilities?: ModelCapabilities;
  metadata?: Record<string, unknown>;
}