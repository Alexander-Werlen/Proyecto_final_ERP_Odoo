from odoo import fields, models


class SupplierPaymentMethod(models.Model):
    _name = 'supplier_payment_method'
    _description = 'Método de pago a proveedor'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)
    account_number = fields.Char(string='Número de cuenta')

    _sql_constraints = [
        (
            'supplier_payment_method_name_uniq',
            'UNIQUE(name)',
            'Ya existe un método de pago a proveedor con este nombre.',
        ),
    ]
