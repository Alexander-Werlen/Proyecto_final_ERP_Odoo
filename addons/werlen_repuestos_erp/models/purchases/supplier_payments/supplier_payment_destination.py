from odoo import api, fields, models


class SupplierPaymentDestination(models.Model):
    _name = 'supplier_payment_destination'
    _description = 'Destino de pago a proveedor'
    _rec_name = 'name'
    _order = 'partner_id, name'

    partner_id = fields.Many2one(
        comodel_name='res.partner', string='Proveedor', required=True, index=True,
        domain=[('is_supplier', '=', True)], ondelete='restrict',
    )
    bank_name = fields.Char(string='Nombre del banco', required=True)
    bank_number = fields.Char(string='Número de banco')
    cvu = fields.Char(string='CVU')
    account_number = fields.Char(string='Número de cuenta del proveedor')
    name = fields.Char(string='Nombre', compute='_compute_name', store=True)

    @api.depends('bank_name', 'bank_number', 'cvu', 'account_number')
    def _compute_name(self):
        for record in self:
            parts = [record.bank_name, record.bank_number, record.cvu, record.account_number]
            record.name = ' - '.join(part for part in parts if part)
