from odoo import models, fields, api
from odoo.exceptions import UserError

class PaymentMethod(models.Model):
    _name = 'payment_method'
    _rec_name = 'name'
    _description = "Registro de: Metodo de pago"

    name = fields.Char(
        string="Metodo de pago",
        required=True,
    )

    active_currently = fields.Boolean(
        string="Activo",
        default=True,
        help=(
            "Los métodos de pago activos se muestran como opciones al crear pagos manualmente. "
            "Un método de pago debe establecerse como NO activo cuando ya no será utilizado."
        ),
        index=True
    )

    is_account_payment_method = fields.Boolean(
        string="Es método de Cuenta Corriente",
        default=False,
        help="Nunca se debe crear un pago con este método. \nSolo se usa para definir la factura como cuenta corriente."
    )

    billing_coefficient = fields.Float(
        string="Coeficiente facturación base",
        default=1.0,
        digits=(16, 4),
        help=(
            "Porcentaje del importe fiscal que representa el valor base "
            "de los productos vendidos. Ej: 0,85 = 85%."
        ),
        required=True
    )

    @api.constrains('billing_coefficient')
    def _check_billing_coefficient(self):
        for rec in self:
            if rec.billing_coefficient <= 0 or rec.billing_coefficient > 1:
                raise UserError("El coeficiente debe ser mayor a 0 y menor o igual a 1.")

    """ SQL Constraints """

    _sql_constraints = [

        # Identificador único del método de pago
        (
            'payment_method_name_uniq',
            'unique(name)',
            'Ya existe un método de pago con este nombre.'
        ),

        # Required: name
        (
            'payment_method_name_not_null',
            'CHECK(name IS NOT NULL)',
            'El nombre del método de pago es obligatorio.'
        ),

        # Required: billing_coefficient
        (
            'payment_method_billing_coefficient_not_null',
            'CHECK(billing_coefficient IS NOT NULL)',
            'El coeficiente de facturación es obligatorio.'
        ),

        # El coeficiente debe ser mayor que 0
        (
            'payment_method_billing_coefficient_positive',
            'CHECK(billing_coefficient >= 0)',
            'El coeficiente de facturación no puede ser menor que cero.'
        ),

        # Evitar coeficientes absurdos (ej. > 1 = más del 100%)
        (
            'payment_method_billing_coefficient_max',
            'CHECK(billing_coefficient <= 1)',
            'El coeficiente de facturación no puede ser mayor a 1.'
        ),

    ]
