# The providers a5s's Azure infrastructure uses. Commit .terraform.lock.hcl from the first
# init with an account, so every later init gets exactly the same providers.
terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.14"
    }

    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Where the state is kept: a storage account of its own, which only the people who apply
  # this may read, since the state holds the passwords it makes. Given at init, with
  # terraform init -backend-config=backend.hcl (README.md).
  backend "azurerm" {}
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }

  subscription_id     = var.subscription_id
  storage_use_azuread = true
}
