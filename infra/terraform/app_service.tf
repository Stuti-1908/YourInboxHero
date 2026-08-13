resource "azurerm_service_plan" "plan" {
  name                = "yourinboxhero-plan-${var.environment}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "P1v2"
}

resource "azurerm_linux_web_app" "api" {
  name                = "yourinboxhero-api-${var.environment}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  service_plan_id     = azurerm_service_plan.plan.id
  https_only          = true

  site_config {
    application_stack {
      docker_image_name   = "${var.acr_name}.azurecr.io/yourinboxhero:${var.image_tag}"
      docker_registry_url = "https://${var.acr_name}.azurecr.io"
    }
    cors {
      allowed_origins = ["https://app.yourinboxhero.com"]
    }
  }
  
  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_linux_web_app_slot" "green" {
  name           = "green"
  app_service_id = azurerm_linux_web_app.api.id
  
  site_config {
    application_stack {
      docker_image_name   = "${var.acr_name}.azurecr.io/yourinboxhero:${var.image_tag}"
      docker_registry_url = "https://${var.acr_name}.azurecr.io"
    }
  }
  
  identity {
    type = "SystemAssigned"
  }
}
