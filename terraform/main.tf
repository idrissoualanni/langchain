terraform {
  required_providers {
    render = {
      source  = "render-corp/render"
      version = "~> 1.0" # Adjust based on actual provider version
    }
    neon   = {
      source  = "neontech/neon"
      version = "~> 1.0" # Adjust based on actual provider version
    }
  }
}

provider "render" {
  api_key = var.render_api_key
}

provider "neon" {
  api_key = var.neon_api_key
}

# Neon Project
resource "neon_project" "agent_tutor" {
  name = "agent-tutor"
}

# Neon Branch for Production
resource "neon_branch" "main" {
  project_id = neon_project.agent_tutor.id
  name       = "main"
}

# Neon Branch for Staging
resource "neon_branch" "staging" {
  project_id = neon_project.agent_tutor.id
  name       = "staging"
}

# Render Web Service (API)
resource "render_web_service" "api_production" {
  name      = "agent-tutor-api"
  plan      = "starter"
  region    = "frankfurt" # Example region
  runtime   = "python"
  repo      = "https://github.com/your-repo/agent-tutor"
  branch    = "master"

  env_vars = {
    APP_ENV            = "production"
    DATABASE_URL       = neon_branch.main.connection_string
    API_CORS_ORIGINS   = var.prod_cors_origins
    # Other secrets passed via variables
    TAVILY_API_KEY     = var.tavily_api_key
    OPENAI_API_KEY     = var.openai_api_key
  }
}

# Render Web Service (API Staging)
resource "render_web_service" "api_staging" {
  name      = "agent-tutor-api-staging"
  plan      = "starter"
  region    = "frankfurt"
  runtime   = "python"
  repo      = "https://github.com/your-repo/agent-tutor"
  branch    = "staging" # Assuming a staging branch exists

  env_vars = {
    APP_ENV            = "staging"
    DATABASE_URL       = neon_branch.staging.connection_string
    API_CORS_ORIGINS   = var.staging_cors_origins
    TAVILY_API_KEY     = var.tavily_api_key
    OPENAI_API_KEY     = var.openai_api_key
  }
}
