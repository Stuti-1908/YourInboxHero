terraform {
  backend "azurerm" {
    resource_group_name   = "tfstate-rg"
    storage_account_name  = "tfstateaccount"
    container_name        = "tfstate"
    key                   = "yourinboxhero.tfstate"
  }
}
