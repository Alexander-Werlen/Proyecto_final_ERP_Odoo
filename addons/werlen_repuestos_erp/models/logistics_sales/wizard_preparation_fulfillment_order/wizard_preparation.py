from odoo import models, fields

class WizardPreparation(models.TransientModel):
    _name = 'wizard_preparation'
    _description = 'Ayudante para: Preparación de Venta'

    saler_order_ids = fields.Many2many(
        'sale_fulfillment_order', 
        string='Ventas'
    )

    packages_count = fields.Char(
        string='Cantidad de paquetes', 
        default="1 bulto"
    )

    def action_confirm(self):
        for sale_fulfillment_order in self.saler_order_ids:
            sale_fulfillment_order.finish_preparation()
            sale_fulfillment_order.sudo().with_context(workflow_transition=True).write({'packages_count': self.packages_count})

