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

# Resource group (example)
resource "azurerm_resource_group" "rg" {
  name     = "yourinboxhero-rg"
  location = "East US"
}