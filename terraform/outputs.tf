output "neon_project_id" {
  description = "The ID of the Neon project"
  value       = neon_project.agent_tutor.id
}

output "prod_db_connection_string" {
  description = "Connection string for production database"
  value       = neon_branch.main.connection_string
  sensitive   = true
}

output "staging_db_connection_string" {
  description = "Connection string for staging database"
  value       = neon_branch.staging.connection_string
  sensitive   = true
}

output "api_production_url" {
  description = "URL of the production API"
  value       = render_web_service.api_production.url
}

output "api_staging_url" {
  description = "URL of the staging API"
  value       = render_web_service.api_staging.url
}
