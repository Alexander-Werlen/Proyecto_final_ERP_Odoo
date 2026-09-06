from odoo import api, fields, models

from ....enums.accounting.payment_origin_explanation import PAYMENT_ORIGIN_EXPLANATION_ENUM
from ....utils.group_verification import display_warning_toast, ensure_user_in_groups


class WizardCurrentAccountIncome(models.TransientModel):
    _name = 'wizard_current_account_income'
    _description = 'Ayudante para: Ingreso a cuenta corriente'

    payment_method_id = fields.Many2one('payment_method', string='Método de pago', required=True)
    journal_id = fields.Many2one('journal', string='Diario', required=True)
    amount = fields.Monetary(string='Importe', required=True)
    payer_id = fields.Many2one('res.partner', string='Paga', required=True)
    payment_origin_explanation = fields.Selection(
        selection=PAYMENT_ORIGIN_EXPLANATION_ENUM,
        default='account_in',
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    observations = fields.Text(string='Observaciones')
    account_payment_for_auto_reconciliation = fields.Many2one(
        'account_payment',
        string='Recibo a reconciliar automáticamente',
        readonly=True,
    )

    @api.onchange('payment_method_id')
    def _onchange_payment_method(self):
        for record in self:
            if not record.payment_method_id:
                record.journal_id = False
            elif record.journal_id not in record.payment_method_id.allowed_journals:
                record.journal_id = record.payment_method_id.get_default_journal(self.env.user)

    def action_create_payment_line(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            [
                'werlen_repuestos_erp.group_sales',
                'werlen_repuestos_erp.group_accountant',
            ],
            error_message='Necesitas permisos de Ventas o Caja para registrar ingresos a cuenta corriente.',
        )
        if self.amount <= 0:
            return display_warning_toast('Monto inválido', 'El monto debe ser mayor que 0.')
        if not self.payment_method_id or not self.journal_id:
            return display_warning_toast('Datos faltantes', 'Debe seleccionar método de pago y diario.')
        payment = self.env['payment_line'].sudo().create({
            'amount': self.amount,
            'is_outgoing': False,
            'payment_method': self.payment_method_id.id,
            'journal': self.journal_id.id,
            'confirmed': False,
            'payer': self.payer_id.id,
            'payee': self.company_id.partner_id.id,
            'payment_origin_explanation': 'account_in',
            'observations': self.observations,
        })
        if self.account_payment_for_auto_reconciliation:
            self.env['reconciliation_line'].sudo().create({
                'outgoing_move_ref': f'account_payment,{self.account_payment_for_auto_reconciliation.id}',
                'incomming_move_ref': f'payment_line,{payment.id}',
                'amount': self.amount,
                'confirmed': True,
            })
        return {'type': 'ir.actions.act_window_close'}
