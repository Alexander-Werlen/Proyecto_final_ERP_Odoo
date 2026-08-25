from odoo import api, fields, models
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
            "Los métodos de pago activos se muestran como opciones al crear facturas manualmente. "
            "Un método de pago debe establecerse como NO activo cuando ya no será utilizado."
        ),
        index=True
    )

    allowed_journals = fields.Many2many(
        comodel_name='journal',
        relation='payment_method_journal_rel',
        column1='payment_method_id',
        column2='journal_id',
        string='Diarios permitidos',
    )

    default_journal = fields.Many2one(
        comodel_name='journal',
        string='Diario por defecto',
        ondelete='restrict',
    )

    cash_closing_category_id = fields.Many2one(
        comodel_name='cash_closing_category',
        string='Categoría de cierre',
        ondelete='restrict',
        required=True,
    )

    is_account_payment_method = fields.Boolean(
        string='Es método de Cuenta Corriente',
        default=False,
        help='Sólo identifica ventas a cuenta corriente; no crea pagos automáticamente.',
    )

    billing_coefficient = fields.Float(
        string='Coeficiente de facturación base',
        default=1.0,
        digits=(16, 4),
        required=True,
    )

    @api.constrains('billing_coefficient')
    def _check_billing_coefficient(self):
        for record in self:
            if record.billing_coefficient <= 0 or record.billing_coefficient > 1:
                raise UserError('El coeficiente debe ser mayor que 0 y menor o igual a 1.')

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

        (
            'payment_method_cash_closing_category_not_null',
            'CHECK(cash_closing_category_id IS NOT NULL)',
            'La categoría de cierre es obligatoria.',
        ),

        (
            'payment_method_billing_coefficient_not_null',
            'CHECK(billing_coefficient IS NOT NULL)',
            'El coeficiente de facturación es obligatorio.',
        ),

    ]
