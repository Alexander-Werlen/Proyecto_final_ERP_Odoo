from odoo import fields, models

from ....utils.group_verification import ensure_user_in_groups


class WizardConfirmSupplierPaymentUse(models.TransientModel):
    _name = 'wizard_confirm_supplier_payment_use'
    _description = 'Confirmar uso de pago a proveedor'

    supplier_payment_id = fields.Many2one(
        comodel_name='supplier_payment', string='Pago a proveedor',
        required=True, readonly=True,
    )
    use_date = fields.Date(string='Fecha de uso', required=True)
    related_payment_orders = fields.Text(string='Órdenes de pago relacionadas')
    observations = fields.Text(string='Observaciones')

    def action_confirm(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user, ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para confirmar el uso de un pago a proveedor.',
        )
        self.supplier_payment_id.write({
            'state': 'used',
            'use_date': self.use_date,
            'related_payment_orders': self.related_payment_orders,
            'observations': self.observations,
        })
        return {'type': 'ir.actions.act_window_close'}
