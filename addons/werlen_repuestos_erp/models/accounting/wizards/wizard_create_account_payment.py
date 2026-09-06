from odoo import fields, models

from ....utils.group_verification import display_warning_toast, ensure_user_in_groups


class WizardCreateAccountPayment(models.TransientModel):
    _name = 'wizard_create_account_payment'
    _description = 'Wizard para crear recibos manualmente'

    account_payment_id = fields.Char(string='Número de recibo', required=True)
    client = fields.Many2one('res.partner', string='Cliente', required=True)
    amount = fields.Monetary(string='Importe', required=True)
    discount_amount = fields.Monetary(string='Descuento', required=True, default=0.0)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now, required=True)

    def action_create_account_payment(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_administration'],
            error_message='Necesitas permisos de Administración para crear recibos.',
        )
        if self.amount <= 0 or self.discount_amount < 0:
            return display_warning_toast('Importe inválido', 'El importe debe ser positivo y el descuento no puede ser negativo.')
        payment = self.env['account_payment'].create({
            'account_payment_id': self.account_payment_id,
            'client': self.client.id,
            'amount': self.amount,
            'discount_amount': self.discount_amount,
            'date': self.date,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account_payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }
