from odoo import fields, models


class CashClosingCategory(models.Model):
    _name = 'cash_closing_category'
    _description = 'Registro de: Categoría de cierre de caja'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)

    payment_method_ids = fields.One2many(
        comodel_name='payment_method',
        inverse_name='cash_closing_category_id',
        string='Métodos de pago',
    )

    active_currently = fields.Boolean(string='Activo', default=True)

    _sql_constraints = [
        (
            'cash_closing_category_name_uniq',
            'UNIQUE(name)',
            'El nombre de la categoría debe ser único.',
        ),
    ]
