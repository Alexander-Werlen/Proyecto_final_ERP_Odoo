from odoo import fields, models


class WizardCreateClientClaim(models.TransientModel):
    _name = 'wizard_create_client_claim'
    _description = 'Asistente para crear reclamos de cliente'

    claim_date = fields.Date(string='Fecha de reclamo', required=True, default=fields.Date.context_today)
    reason = fields.Text(string='Motivo', required=True)
    product_brand = fields.Char(string='Marca', required=True)
    product_id = fields.Many2one('purchase.product', string='Código del producto', required=True)
    vehicle_description = fields.Char(string='Vehículo')
    sale_fulfillment_order_id = fields.Many2one('sale_fulfillment_order', string='Factura')
    client_name = fields.Char(string='Nombre cliente', required=True)
    client_address = fields.Char(string='Dirección')
    client_phone = fields.Char(string='Teléfono')

    def action_create_client_claim(self):
        self.ensure_one()
        claim = self.env['client_claim'].create({
            'claim_date': self.claim_date, 'reason': self.reason.strip(),
            'product_brand': self.product_brand.strip(), 'product_id': self.product_id.id,
            'vehicle_description': self.vehicle_description.strip() if self.vehicle_description else False,
            'sale_fulfillment_order_id': self.sale_fulfillment_order_id.id or False,
            'client_name': self.client_name.strip(), 'client_address': self.client_address,
            'client_phone': self.client_phone,
        })
        return {'type': 'ir.actions.act_window', 'name': 'Reclamo de cliente',
                'res_model': 'client_claim', 'view_mode': 'form',
                'view_id': self.env.ref('werlen_repuestos_erp.client_claim_form_view').id,
                'res_id': claim.id, 'target': 'current'}
