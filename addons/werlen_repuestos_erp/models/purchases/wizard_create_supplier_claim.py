from odoo import api, fields, models

from ...enums.purchases.supplier_claim_type import SUPPLIER_CLAIM_TYPE_ENUM
from ...utils.group_verification import ensure_user_in_groups, display_warning_toast


class WizardCreateSupplierClaim(models.TransientModel):
    _name = 'wizard_create_supplier_claim'
    _description = 'Asistente para crear reclamos a proveedor'

    claim_type = fields.Selection(SUPPLIER_CLAIM_TYPE_ENUM, string='Tipo de reclamo', required=True)
    supplier_id = fields.Many2one('res.partner', string='Proveedor', required=True,
                                  domain=[('is_supplier', '=', True)])
    product_id = fields.Many2one('purchase.product', string='Producto', required=True)
    list_price = fields.Float(string='Precio de lista')
    quantity = fields.Integer(string='Cantidad', required=True, default=1)
    observations = fields.Text(string='Observaciones')
    purchase_invoice_id = fields.Many2one('purchase_invoice', string='Factura de compra')
    reception_id = fields.Many2one('reception', string='Ingreso de mercadería')
    client_claim_id = fields.Many2one('client_claim', string='Reclamo de cliente', readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        values.setdefault('quantity', 1)
        return values

    def action_create(self):
        self.ensure_one()
        ensure_user_in_groups(self.env.user, ['werlen_repuestos_erp.group_administration'],
                              error_message='No tiene permisos para crear reclamos a proveedor.')
        if self.quantity < 1:
            return display_warning_toast('Cantidad inválida', 'La cantidad debe ser mayor o igual a 1.')
        claims = self.env['supplier_claim']
        for _ in range(self.quantity):
            claims |= self.env['supplier_claim'].create({
                'claim_type': self.claim_type,
                'supplier_id': self.supplier_id.id,
                'product_id': self.product_id.id,
                'list_price': self.list_price,
                'observations': (self.observations or '').strip() or False,
                'purchase_invoice_id': self.purchase_invoice_id.id or False,
                'reception_id': self.reception_id.id or False,
                'client_claim_id': self.client_claim_id.id or False,
            })
        if self.client_claim_id:
            self.client_claim_id.sudo().write({'supplier_claim_id': claims[0].id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reclamos a proveedor',
            'res_model': 'supplier_claim',
            'view_mode': 'list,form',
            'domain': [('id', 'in', claims.ids)],
            'target': 'current',
        }
