variable "db_password" {
  type      = string
  sensitive = true
}

variable "acr_name" {
  type    = string
  default = "yourinboxheroacr"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "environment" {
  type    = string
  default = "production"
}
