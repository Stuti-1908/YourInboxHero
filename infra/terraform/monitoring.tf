resource "azurerm_log_analytics_workspace" "law" {
  name                = "yourinboxhero-law-${var.environment}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "appinsights" {
  name                = "yourinboxhero-appinsights-${var.environment}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  workspace_id        = azurerm_log_analytics_workspace.law.id
  application_type    = "web"
}

resource "azurerm_monitor_metric_alert" "http5xx_alert" {
  name                = "api-http5xx-alert"
  resource_group_name = azurerm_resource_group.rg.name
  scopes              = [azurerm_linux_web_app.api.id]
  description         = "Action will be triggered when Http5xx > 10"

  criteria {
    metric_namespace = "Microsoft.Web/sites"
    metric_name      = "Http5xx"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 10
  }

  action {
    action_group_id = azurerm_monitor_action_group.ag.id
  }
}

resource "azurerm_monitor_action_group" "ag" {
  name                = "CriticalAlertsActionGroup"
  resource_group_name = azurerm_resource_group.rg.name
  short_name          = "crit-ag"

  email_receiver {
    name          = "sendtoadmin"
    email_address = "admin@yourinboxhero.com"
  }
}
