# Deploys from GitHub: an identity GitHub Actions signs in as with its own OpenID Connect token,
# from this repository's environment alone, so no cloud key is stored anywhere. It may move
# the apps and the setup job to a new image, and nothing else (.github/workflows/deploy-azure.yml).
# Terraform itself is applied by a person, after reviewing its plan.

resource "azurerm_user_assigned_identity" "deploy" {
  name                = "id-${local.name}-deploy"
  location            = azurerm_resource_group.a5s.location
  resource_group_name = azurerm_resource_group.a5s.name
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "github" {
  name                = "github-${var.github_environment}"
  resource_group_name = azurerm_resource_group.a5s.name
  parent_id           = azurerm_user_assigned_identity.deploy.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.github_repository}:environment:${var.github_environment}"
}

resource "azurerm_role_assignment" "deploy" {
  for_each = merge(
    { for part, app in azurerm_container_app.part : part => app.id },
    { setup = azurerm_container_app_job.setup.id, environment = azurerm_container_app_environment.a5s.id },
  )

  scope                = each.value
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.deploy.principal_id
  principal_type       = "ServicePrincipal"
}
