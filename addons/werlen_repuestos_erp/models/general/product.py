from odoo import fields, models


class PurchaseProduct(models.Model):
    _name = 'purchase.product'
    _description = 'Producto'
    _order = 'name asc'

    name = fields.Char(string='Código del producto', required=True, index=True)
    description = fields.Text(string='Descripción')

    _sql_constraints = [
        (
            'purchase_product_name_uniq',
            'UNIQUE(name)',
            'El código del producto debe ser único.',
        ),
    ]
