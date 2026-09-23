from odoo import fields, models


class SupplierPaymentSupplier(models.Model):
    _name = 'supplier.payment.supplier'
    _description = 'Proveedor de pago'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True,
    )
