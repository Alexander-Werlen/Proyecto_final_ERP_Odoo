from odoo import models, fields

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
            "Los métodos de pago activos se muestran como opciones al crear facturas manualmente. "
            "Un método de pago debe establecerse como NO activo cuando ya no será utilizado."
        ),
        index=True
    )

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

    ]
