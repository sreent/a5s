variable "subscription_id" {
  description = "The Azure subscription a5s runs in: one for each environment."
  type        = string
}

variable "environment" {
  description = "Which environment this is, such as test or production."
  type        = string
  default     = "test"
}

variable "prefix" {
  description = "What each resource's name starts with."
  type        = string
  default     = "a5s"
}

variable "location" {
  description = "The Azure region, such as uksouth."
  type        = string
}

variable "tags" {
  description = "Tags for every resource, such as who pays for them."
  type        = map(string)
  default     = {}
}

variable "address_space" {
  description = "The virtual network's addresses: a /16 nothing else in the organisation uses."
  type        = string
  default     = "10.40.0.0/16"
}

variable "image" {
  description = "a5s's image, by its digest, as a release published it: ghcr.io/<owner>/a5s@sha256:..."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "Name the image by its digest, so what runs is exactly what was approved."
  }
}

variable "registry_username" {
  description = "Who pulls the image from ghcr.io, if its package is private: else null. Their token goes in Key Vault as registry-password."
  type        = string
  default     = null
}

variable "postgres_sku" {
  description = "Postgres's size: a burstable one for test."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  description = "Postgres's storage."
  type        = number
  default     = 32768
}

variable "ledger_replication" {
  description = "How the ledger's locked copies are replicated: GRS, to another region, in production."
  type        = string
  default     = "LRS"
}

variable "anchor_retain_days" {
  description = "How long each copy of the ledger stays locked: assurance's to set."
  type        = number
  default     = 365
}

variable "team" {
  description = "The directory's team that runs a5s."
  type        = string
  default     = "platform"
}

variable "oidc_issuer" {
  description = "The identity provider people sign in with, such as https://login.microsoftonline.com/<tenant>/v2.0."
  type        = string
}

variable "oidc_audience" {
  description = "The audiences a sign-in may be for, comma-separated."
  type        = string
  default     = "a5s"
}

variable "oidc_person_claim" {
  description = "The claim that names the person: oid, for Entra ID."
  type        = string
  default     = "oid"
}

variable "oidc_directory_prefix" {
  description = "How the directory names people by that claim, such as entra for entra:<oid>."
  type        = string
  default     = "entra"
}

variable "webchat_client_id" {
  description = "The web chat's client at the identity provider: a public client, with PKCE."
  type        = string
}

variable "public_url" {
  description = "Where people reach the channels, if not at the channels app's own address."
  type        = string
  default     = null
}

variable "teams_tenant_id" {
  description = "The Microsoft 365 tenant a5s's bots are registered in: a test tenant of its own, for test. Null for no Teams."
  type        = string
  default     = null
}

variable "teams_bots" {
  description = "Each agent's bot's app id in that tenant, such as { assistant = \"<app id>\" }. Each bot's secret goes in Key Vault as teams-secret-<agent>."
  type        = map(string)
  default     = {}
}

variable "github_repository" {
  description = "The repository whose deploys may update the apps, such as owner/a5s."
  type        = string
}

variable "github_environment" {
  description = "The GitHub environment those deploys run in."
  type        = string
  default     = "azure-test"
}

variable "budget_amount" {
  description = "The month's spending, in the subscription's currency, past which people are told."
  type        = number
  default     = 300
}

variable "budget_emails" {
  description = "Who's told as spending passes 80% and 100% of the budget."
  type        = list(string)
}
