# Terraform configuration for YourInboxHero
# This file will be expanded in subsequent tasks.

# Provider configuration
terraform {
  required_version = ">= 1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~>3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# Resource group
resource "azurerm_resource_group" "rg" {
  name     = "yourinboxhero-rg-${var.environment}"
  location = "East US"
}

resource "azurerm_postgresql_flexible_server" "db" {
  name                   = "yourinboxhero-pg-${var.environment}"
  resource_group_name    = azurerm_resource_group.rg.name
  location               = azurerm_resource_group.rg.location
  version                = "15"
  sku_name               = "B_Standard_B2ms"
  storage_mb             = 32768
  administrator_login    = "adminuser"
  administrator_password = var.db_password
  
  high_availability {
    mode = "ZoneRedundant"
  }
}

resource "azurerm_postgresql_flexible_server_database" "app_db" {
  name      = "appdb"
  server_id = azurerm_postgresql_flexible_server.db.id
  collation = "en_US.utf8"
  charset   = "utf8"
}