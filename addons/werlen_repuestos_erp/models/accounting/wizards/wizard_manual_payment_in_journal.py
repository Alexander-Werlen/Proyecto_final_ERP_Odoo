from odoo import fields, models

from ....enums.accounting.payment_origin_explanation import PAYMENT_ORIGIN_EXPLANATION_ENUM
from ....utils.group_verification import display_warning_toast, ensure_user_in_groups


class WizardManualPaymentInJournal(models.TransientModel):
    _name = 'wizard_manual_payment_in_journal'
    _description = 'Ayudante para: Registrar pago entrante al diario'

    payment_method = fields.Many2one('payment_method', string='Método de pago', required=True)
    journal = fields.Many2one('journal', string='Diario', required=True)
    amount = fields.Monetary(string='Importe', required=True)
    observations = fields.Text(string='Observaciones', required=True)
    payer = fields.Many2one('res.partner', string='Paga', required=True)
    payment_origin_explanation = fields.Selection(
        selection=PAYMENT_ORIGIN_EXPLANATION_ENUM,
        string='Razón del pago',
        default='non_operational',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')

    def action_confirm(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja para registrar movimientos.',
        )
        if self.amount <= 0:
            return display_warning_toast('Monto inválido', 'El monto debe ser mayor que 0.')
        if not self.observations:
            return display_warning_toast('Observaciones faltantes', 'Debe justificar el movimiento.')
        self.env['payment_line'].create({
            'amount': self.amount,
            'is_outgoing': False,
            'payment_method': self.payment_method.id,
            'journal': self.journal.id,
            'confirmed': True,
            'payer': self.payer.id,
            'payee': self.company_id.partner_id.id,
            'payment_origin_explanation': self.payment_origin_explanation,
            'observations': self.observations,
        })
        return {'type': 'ir.actions.act_window_close'}
