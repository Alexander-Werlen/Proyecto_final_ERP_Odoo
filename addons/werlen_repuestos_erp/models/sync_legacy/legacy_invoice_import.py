from odoo import fields, models


class LegacyInvoiceImport(models.Model):
    _name = "legacy_invoice_import"
    _description = "Registro de sincronización de comprobantes externos"
    _order = "create_date desc"

    filename = fields.Char(required=True, string="Archivo")
    path = fields.Char(required=True, string="Ruta")
    state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("processing", "Procesando"),
            ("done", "Exitoso"),
            ("retry", "Reintentar"),
            ("failed", "Fallido"),
        ],
        default="pending",
        required=True,
        string="Estado",
    )
    attempts = fields.Integer(default=0, string="Cantidad de intentos")
    last_error = fields.Text(string="Descripción del último error")
    correlation_id = fields.Char(index=True, string="Identificador")
    last_attempt_at = fields.Datetime(string="Último intento")
