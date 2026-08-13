resource "azurerm_servicebus_namespace" "sb" {
  name                = "yourinboxhero-sb-${var.environment}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "Standard"
}

resource "azurerm_servicebus_queue" "reminder_queue" {
  name                                    = "reminder-queue"
  namespace_id                            = azurerm_servicebus_namespace.sb.id
  requires_duplicate_detection            = true
  duplicate_detection_history_time_window = "PT24H" # Keep 24 hours of history for daily batch deductions
}
