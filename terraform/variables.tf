variable "render_api_key" {
  description = "API Key for Render"
  type        = string
  sensitive   = true
}

variable "neon_api_key" {
  description = "API Key for Neon"
  type        = string
  sensitive   = true
}

variable "prod_cors_origins" {
  description = "CORS Origins for production"
  type        = string
  default     = ""
}

variable "staging_cors_origins" {
  description = "CORS Origins for staging"
  type        = string
  default     = ""
}

variable "tavily_api_key" {
  description = "Tavily API Key"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API Key"
  type        = string
  sensitive   = true
}
