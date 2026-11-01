# a5s's parts, as in deploy/compose.yaml: the gateway, in the trusted core, reached only from
# inside the environment; the channels, the only part people reach; the scheduler; the
# ledger's copier; and the worker, which holds no secrets. And the setup job, which sets up
# the schema and applies the signed settings, run before each new image takes over.

locals {
  public_url = coalesce(var.public_url, "https://ca-${local.name}-channels.${azurerm_container_app_environment.a5s.default_domain}")

  identity_of = { for part, identity in azurerm_user_assigned_identity.part : part => identity.id }

  people = tomap({
    A5S_OIDC_ISSUER           = var.oidc_issuer
    A5S_OIDC_AUDIENCE         = var.oidc_audience
    A5S_OIDC_PERSON_CLAIM     = var.oidc_person_claim
    A5S_OIDC_DIRECTORY_PREFIX = var.oidc_directory_prefix
    A5S_WEBCHAT_CLIENT_ID     = var.webchat_client_id
    A5S_PUBLIC_URL            = local.public_url
  })

  # Teams: each agent's bot, by its app id, and the variable its secret is in
  teams = var.teams_tenant_id == null ? tomap({}) : tomap({
    A5S_TEAMS_TENANT_ID = var.teams_tenant_id
    A5S_TEAMS_BOTS      = jsonencode([for agent, app_id in var.teams_bots : { agent = agent, app_id = app_id, secret_env = "A5S_TEAMS_SECRET_${upper(agent)}" }])
  })

  bots = tomap({ for agent in keys(var.teams_bots) : "A5S_TEAMS_SECRET_${upper(agent)}" => "teams-secret-${agent}" if var.teams_tenant_id != null })

  apps = {
    gateway = {
      args   = tolist(["gateway", "--host", "0.0.0.0"])
      port   = 8700
      public = false
      env    = merge(local.people, local.teams, tomap({ A5S_TEAM = var.team }))

      secrets = merge(local.bots, tomap({
        A5S_DATABASE_URL  = "db-gateway-url"
        A5S_SERVICE_TOKEN = "service-token"
        A5S_SEAL_KEYS     = "seal-keys"
        DEEPSEEK_API_KEY  = "deepseek-api-key"
        QWEN_API_KEY      = "qwen-api-key"
      }))
    }

    channels = {
      args   = tolist(["channels", "--host", "0.0.0.0"])
      port   = 8703
      public = true
      env    = merge(local.people, local.teams)

      secrets = merge(local.bots, tomap({
        A5S_DATABASE_URL = "db-channels-url"
        A5S_SEAL_KEYS    = "seal-keys"
      }))
    }

    scheduler = {
      args   = tolist(["scheduler"])
      port   = null
      public = false

      env = tomap({
        A5S_GATEWAY_URL = "http://ca-${local.name}-gateway"
        A5S_WORKER_URL  = "http://ca-${local.name}-worker"
      })

      secrets = tomap({
        A5S_DATABASE_URL  = "db-scheduler-url"
        A5S_SERVICE_TOKEN = "service-token"
      })
    }

    anchor = {
      args   = tolist(["anchor", "--every", "3600"])
      port   = null
      public = false

      env = tomap({
        A5S_ANCHOR_STORE       = "azure://${azurerm_storage_account.ledger.name}/${azurerm_storage_container.ledger.name}/${var.environment}"
        A5S_ANCHOR_RETAIN_DAYS = tostring(var.anchor_retain_days)
        AZURE_CLIENT_ID        = azurerm_user_assigned_identity.part["anchor"].client_id
      })

      secrets = tomap({
        A5S_DATABASE_URL = "db-anchor-url"
      })
    }

    worker = {
      args    = tolist(["worker", "--host", "0.0.0.0"])
      port    = 8702
      public  = false
      env     = tomap({ A5S_GATEWAY_URL = "http://ca-${local.name}-gateway" })
      secrets = tomap({})
    }
  }
}

resource "azurerm_container_app" "part" {
  for_each                     = local.apps
  name                         = "ca-${local.name}-${each.key}"
  container_app_environment_id = azurerm_container_app_environment.a5s.id
  resource_group_name          = azurerm_resource_group.a5s.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.tags

  dynamic "identity" {
    for_each = length(local.reads[each.key]) > 0 ? [local.identity_of[each.key]] : []

    content {
      type         = "UserAssigned"
      identity_ids = [identity.value]
    }
  }

  dynamic "secret" {
    for_each = toset(local.reads[each.key])

    content {
      name                = secret.value
      key_vault_secret_id = local.secret_ids[secret.value].versionless_id
      identity            = local.identity_of[each.key]
    }
  }

  dynamic "registry" {
    for_each = var.registry_username == null ? [] : [var.registry_username]

    content {
      server               = "ghcr.io"
      username             = registry.value
      password_secret_name = "registry-password"
    }
  }

  dynamic "ingress" {
    for_each = each.value.port == null ? [] : [each.value]

    content {
      external_enabled = ingress.value.public
      target_port      = ingress.value.port
      transport        = "http"

      traffic_weight {
        latest_revision = true
        percentage      = 100
      }
    }
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = each.key
      image  = var.image
      args   = each.value.args
      cpu    = 0.5
      memory = "1Gi"

      dynamic "env" {
        for_each = each.value.env

        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = each.value.secrets

        content {
          name        = env.key
          secret_name = env.value
        }
      }
    }
  }

  depends_on = [azurerm_role_assignment.reads, azurerm_role_assignment.ledger]
}

resource "azurerm_container_app_job" "setup" {
  name                         = "caj-${local.name}-setup"
  location                     = azurerm_resource_group.a5s.location
  resource_group_name          = azurerm_resource_group.a5s.name
  container_app_environment_id = azurerm_container_app_environment.a5s.id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 1800
  replica_retry_limit          = 0
  tags                         = local.tags

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [local.identity_of["setup"]]
  }

  dynamic "secret" {
    for_each = toset(local.reads["setup"])

    content {
      name                = secret.value
      key_vault_secret_id = local.secret_ids[secret.value].versionless_id
      identity            = local.identity_of["setup"]
    }
  }

  dynamic "registry" {
    for_each = var.registry_username == null ? [] : [var.registry_username]

    content {
      server               = "ghcr.io"
      username             = registry.value
      password_secret_name = "registry-password"
    }
  }

  template {
    container {
      name   = "setup"
      image  = var.image
      args   = ["setup"]
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "A5S_TEAM"
        value = var.team
      }

      env {
        name        = "A5S_DATABASE_URL"
        secret_name = "db-admin-url"
      }

      dynamic "env" {
        for_each = toset(local.parts)

        content {
          name        = "A5S_DB_${upper(env.value)}_PASSWORD"
          secret_name = "db-${env.value}-password"
        }
      }
    }
  }

  depends_on = [azurerm_role_assignment.reads]
}

# Teams: an Azure Bot for each agent, single-tenant, in the tenant a5s's bots are registered
# in, sending what people write to the channels.

resource "azurerm_bot_service_azure_bot" "agent" {
  for_each                = var.teams_tenant_id == null ? tomap({}) : var.teams_bots
  name                    = "bot-${local.name}-${each.key}"
  resource_group_name     = azurerm_resource_group.a5s.name
  location                = "global"
  sku                     = "F0"
  microsoft_app_id        = each.value
  microsoft_app_type      = "SingleTenant"
  microsoft_app_tenant_id = var.teams_tenant_id
  endpoint                = "${local.public_url}/channels/teams/messages"
  tags                    = local.tags
}

resource "azurerm_bot_channel_ms_teams" "agent" {
  for_each            = azurerm_bot_service_azure_bot.agent
  bot_name            = each.value.name
  location            = each.value.location
  resource_group_name = azurerm_resource_group.a5s.name
}
