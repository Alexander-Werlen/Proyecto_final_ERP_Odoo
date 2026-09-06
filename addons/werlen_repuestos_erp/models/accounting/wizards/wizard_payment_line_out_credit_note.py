from odoo import api, fields, models

from ....utils.group_verification import display_warning_toast, ensure_user_in_groups


class WizardPaymentLineOutCreditNote(models.TransientModel):
    _name = 'wizard_payment_line_out_credit_note'
    _description = 'Ayudante para: Reembolsar nota de crédito'

    credit_note_out_id = fields.Many2one('credit_note_out', string='Nota de crédito', required=True)
    payment_method = fields.Many2one('payment_method', string='Método de pago', required=True)
    journal = fields.Many2one('journal', string='Diario', required=True)
    amount = fields.Monetary(string='Importe', required=True)
    credit_note_out_total_amount = fields.Monetary(related='credit_note_out_id.total_amount', string='Total')
    credit_note_out_amount_reconciliated = fields.Monetary(
        related='credit_note_out_id.amount_reconciliated_unconfirmed',
        string='Importe reconciliado',
    )
    credit_note_out_amount_not_reconciliated = fields.Monetary(
        related='credit_note_out_id.amount_not_reconciliated_unconfirmed',
        string='Importe no reconciliado',
    )
    payee = fields.Many2one('res.partner', string='Recibe', required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        for record in self:
            if not record.payment_method:
                record.journal = False
            elif record.journal not in record.payment_method.allowed_journals:
                record.journal = record.payment_method.default_journal or record.payment_method.allowed_journals[:1]

    def action_confirm(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja para reembolsar notas de crédito.',
        )
        if self.credit_note_out_id.state != 'verified':
            return display_warning_toast(
                'Nota no verificada',
                'Sólo se pueden reembolsar notas de crédito verificadas.',
            )
        if self.amount <= 0 or self.amount > self.credit_note_out_amount_not_reconciliated:
            return display_warning_toast(
                'Monto inválido',
                'El importe debe ser positivo y no superar el saldo de la nota de crédito.',
            )
        payment = self.env['payment_line'].create({
            'amount': self.amount,
            'is_outgoing': True,
            'payment_method': self.payment_method.id,
            'journal': self.journal.id,
            'confirmed': True,
            'payer': self.company_id.partner_id.id,
            'payee': self.payee.id,
            'payment_origin_explanation': 'payment_for_credit_note_out',
        })
        self.env['reconciliation_line'].create({
            'outgoing_move_ref': f'payment_line,{payment.id}',
            'incomming_move_ref': f'credit_note_out,{self.credit_note_out_id.id}',
            'amount': self.amount,
            'confirmed': True,
        })
        return {'type': 'ir.actions.act_window_close'}
