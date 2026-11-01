output "channels_url" {
  description = "Where people reach a5s: the web chat, and the address the bots send Teams to."
  value       = local.public_url
}

output "resource_group" {
  description = "AZURE_RESOURCE_GROUP, for the deploy workflow's environment."
  value       = azurerm_resource_group.a5s.name
}

output "name" {
  description = "A5S_NAME, for the deploy workflow's environment: what the apps' names are made from."
  value       = local.name
}

output "deploy_client_id" {
  description = "AZURE_CLIENT_ID, for the deploy workflow's environment."
  value       = azurerm_user_assigned_identity.deploy.client_id
}

output "tenant_id" {
  description = "AZURE_TENANT_ID, for the deploy workflow's environment."
  value       = data.azurerm_client_config.current.tenant_id
}

output "key_vault" {
  description = "Where people set the secrets Terraform doesn't make: README.md says which."
  value       = azurerm_key_vault.a5s.name
}

output "ledger_store" {
  description = "Where the ledger's locked copies go."
  value       = local.apps["anchor"].env["A5S_ANCHOR_STORE"]
}
