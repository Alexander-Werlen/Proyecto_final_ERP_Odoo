from odoo import fields, models

from ....utils.group_verification import ensure_user_in_groups


class WizardChangePaymentLineJournal(models.TransientModel):
    _name = 'wizard_change_payment_line_journal'
    _description = 'Ayudante para: Cambiar diario de pago'

    payment_line_id = fields.Many2one('payment_line', string='Pago', required=True, readonly=True)
    payment_line_amount = fields.Monetary(related='payment_line_id.amount', string='Importe', readonly=True)
    current_journal_id = fields.Many2one('journal', string='Diario actual', readonly=True)
    new_journal_id = fields.Many2one('journal', string='Nuevo diario', required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')

    def action_confirm(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para cambiar el diario.',
        )
        if self.new_journal_id not in self.payment_line_id.payment_method.allowed_journals:
            raise ValueError('El nuevo diario no está permitido para el método de pago.')
        self.payment_line_id.sudo().write({
            'journal': self.new_journal_id.id,
        })
        return {'type': 'ir.actions.act_window_close'}
