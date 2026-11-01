# a5s on Azure: its services as Container Apps in a virtual network, Postgres as a Flexible
# Server only that network reaches, its secrets in Key Vault, each read only by the part
# that needs it, and the ledger's copies in Blob Storage that locks each one. README.md says
# what to do before the first apply, and what's still to decide.

locals {
  name = "${var.prefix}-${var.environment}"
  tags = merge(var.tags, { app = "a5s", environment = var.environment })
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 4
  special = false
  upper   = false
}

resource "azurerm_resource_group" "a5s" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_log_analytics_workspace" "a5s" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.a5s.location
  resource_group_name = azurerm_resource_group.a5s.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

# The network: the apps' environment in one subnet, Postgres in another.

resource "azurerm_virtual_network" "a5s" {
  name                = "vnet-${local.name}"
  location            = azurerm_resource_group.a5s.location
  resource_group_name = azurerm_resource_group.a5s.name
  address_space       = [var.address_space]
  tags                = local.tags
}

resource "azurerm_subnet" "apps" {
  name                 = "apps"
  resource_group_name  = azurerm_resource_group.a5s.name
  virtual_network_name = azurerm_virtual_network.a5s.name
  address_prefixes     = [cidrsubnet(var.address_space, 7, 0)]

  delegation {
    name = "container-apps"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "postgres" {
  name                 = "postgres"
  resource_group_name  = azurerm_resource_group.a5s.name
  virtual_network_name = azurerm_virtual_network.a5s.name
  address_prefixes     = [cidrsubnet(var.address_space, 8, 2)]

  delegation {
    name = "postgres"

    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "postgres" {
  name                = "${local.name}.private.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.a5s.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "postgres"
  resource_group_name   = azurerm_resource_group.a5s.name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.a5s.id
}

# Postgres. a5s's setup job connects as its administrator, makes each part's role, and
# gives each its password; each part then connects as its own role, with only its rights.

resource "random_password" "db" {
  for_each = toset(["admin", "gateway", "channels", "scheduler", "anchor"])
  length   = 40
  special  = false
}

resource "azurerm_postgresql_flexible_server" "a5s" {
  name                          = "psql-${local.name}-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.a5s.name
  location                      = azurerm_resource_group.a5s.location
  version                       = "16"
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  public_network_access_enabled = false
  administrator_login           = "a5s"
  administrator_password        = random_password.db["admin"].result
  sku_name                      = var.postgres_sku
  storage_mb                    = var.postgres_storage_mb
  backup_retention_days         = 7
  tags                          = local.tags

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]

  lifecycle {
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "a5s" {
  name      = "a5s"
  server_id = azurerm_postgresql_flexible_server.a5s.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# Secrets, in Key Vault. Terraform makes the passwords, the service token and the seal key;
# people set the rest after the first apply, and Terraform leaves those alone.

resource "random_password" "service_token" {
  length  = 48
  special = false
}

resource "random_password" "seal_key" {
  length  = 48
  special = false
}

locals {
  parts = ["gateway", "channels", "scheduler", "anchor"]
  db_at = "${azurerm_postgresql_flexible_server.a5s.fqdn}:5432/${azurerm_postgresql_flexible_server_database.a5s.name}?sslmode=require"

  made = merge(
    { for part in local.parts : "db-${part}-url" => "postgresql://a5s_${part}:${random_password.db[part].result}@${local.db_at}" },
    { for part in local.parts : "db-${part}-password" => random_password.db[part].result },
    {
      "db-admin-url"  = "postgresql://a5s:${random_password.db["admin"].result}@${local.db_at}"
      "service-token" = random_password.service_token.result
      "seal-keys"     = random_password.seal_key.result
    },
  )

  # Named apart from their values, which are sensitive, so each secret can be its own resource
  made_names = toset(concat(
    [for part in local.parts : "db-${part}-url"],
    [for part in local.parts : "db-${part}-password"],
    ["db-admin-url", "service-token", "seal-keys"],
  ))

  # Each agent's bot's secret, in the Microsoft 365 tenant its bots are registered in
  teams_secrets = var.teams_tenant_id == null ? [] : [for agent in keys(var.teams_bots) : "teams-secret-${agent}"]

  given = toset(concat(["deepseek-api-key", "qwen-api-key"], local.teams_secrets, local.registry))
}

resource "azurerm_key_vault" "a5s" {
  name                       = "kv-${local.name}-${random_string.suffix.result}"
  location                   = azurerm_resource_group.a5s.location
  resource_group_name        = azurerm_resource_group.a5s.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 90
  tags                       = local.tags
}

# Whoever applies this writes the secrets it makes.
resource "azurerm_role_assignment" "applier" {
  scope                = azurerm_key_vault.a5s.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "made" {
  for_each     = local.made_names
  name         = each.key
  value        = local.made[each.key]
  key_vault_id = azurerm_key_vault.a5s.id

  depends_on = [azurerm_role_assignment.applier]
}

resource "azurerm_key_vault_secret" "given" {
  for_each     = local.given
  name         = each.key
  value        = "unset"
  key_vault_id = azurerm_key_vault.a5s.id

  depends_on = [azurerm_role_assignment.applier]

  lifecycle {
    ignore_changes = [value]
  }
}

# The ledger's copies: Blob Storage that locks each one for its time, which nobody, a5s's
# own identity included, can shorten or delete.

resource "azurerm_storage_account" "ledger" {
  name                            = "st${replace(local.name, "-", "")}${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.a5s.name
  location                        = azurerm_resource_group.a5s.location
  account_tier                    = "Standard"
  account_replication_type        = var.ledger_replication
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  tags                            = local.tags

  blob_properties {
    versioning_enabled = true
  }

  immutability_policy {
    allow_protected_append_writes = false
    state                         = "Unlocked"
    period_since_creation_in_days = 1
  }
}

resource "azurerm_storage_container" "ledger" {
  name                  = "a5s-ledger"
  storage_account_id    = azurerm_storage_account.ledger.id
  container_access_type = "private"
}

# The apps' environment, and an identity for each part. The worker's reads nothing, unless
# the image's package is private, when it reads only the registry's token, as each part does.

resource "azurerm_container_app_environment" "a5s" {
  name                           = "cae-${local.name}"
  location                       = azurerm_resource_group.a5s.location
  resource_group_name            = azurerm_resource_group.a5s.name
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.a5s.id
  infrastructure_subnet_id       = azurerm_subnet.apps.id
  internal_load_balancer_enabled = false
  tags                           = local.tags

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }

  lifecycle {
    ignore_changes = [infrastructure_resource_group_name]
  }
}

resource "azurerm_user_assigned_identity" "part" {
  for_each            = toset(["gateway", "channels", "scheduler", "anchor", "worker", "setup"])
  name                = "id-${local.name}-${each.key}"
  location            = azurerm_resource_group.a5s.location
  resource_group_name = azurerm_resource_group.a5s.name
  tags                = local.tags
}

# Each part reads only its own secrets.
locals {
  registry = var.registry_username == null ? [] : ["registry-password"]

  reads = {
    gateway   = concat(["db-gateway-url", "service-token", "seal-keys", "deepseek-api-key", "qwen-api-key"], local.teams_secrets, local.registry)
    channels  = concat(["db-channels-url", "seal-keys"], local.teams_secrets, local.registry)
    scheduler = concat(["db-scheduler-url", "service-token"], local.registry)
    anchor    = concat(["db-anchor-url"], local.registry)
    worker    = local.registry
    setup     = concat(["db-admin-url", "db-gateway-password", "db-channels-password", "db-scheduler-password", "db-anchor-password"], local.registry)
  }

  secret_ids = merge(
    { for name, s in azurerm_key_vault_secret.made : name => s },
    { for name, s in azurerm_key_vault_secret.given : name => s },
  )

  readings = merge([
    for part, names in local.reads : { for name in names : "${part}/${name}" => { part = part, name = name } }
  ]...)
}

resource "azurerm_role_assignment" "reads" {
  for_each             = local.readings
  scope                = local.secret_ids[each.value.name].resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.part[each.value.part].principal_id
  principal_type       = "ServicePrincipal"
}

# The ledger's copier writes copies and locks them, and nothing else does.
resource "azurerm_role_assignment" "ledger" {
  scope                = "${azurerm_storage_account.ledger.id}/blobServices/default/containers/${azurerm_storage_container.ledger.name}"
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azurerm_user_assigned_identity.part["anchor"].principal_id
  principal_type       = "ServicePrincipal"
}

# What the month costs: people are told at 80% and 100% of the budget.
resource "azurerm_consumption_budget_resource_group" "a5s" {
  name              = "budget-${local.name}"
  resource_group_id = azurerm_resource_group.a5s.id
  amount            = var.budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp())
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThanOrEqualTo"
    contact_emails = var.budget_emails
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    contact_emails = var.budget_emails
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
