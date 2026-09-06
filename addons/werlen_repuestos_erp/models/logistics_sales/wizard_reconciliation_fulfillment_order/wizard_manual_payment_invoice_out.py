from odoo import api, fields, models
from odoo.exceptions import UserError

from ....utils.group_verification import display_warning_toast, ensure_user_in_groups


class WizardManualPaymentInvoiceOut(models.TransientModel):
    _name = 'wizard_manual_payment_invoice_out'
    _description = 'Ayudante para: Registrar pago a factura'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    amount = fields.Monetary(string='Importe', required=True)
    payment_method = fields.Many2one('payment_method', string='Método de pago', required=True)
    journal = fields.Many2one('journal', string='Diario', required=True)
    payer = fields.Many2one('res.partner', string='Pagador', required=True)
    invoice_out_total_amount = fields.Monetary(string='Total factura')
    invoice_out_amount_not_reconciliated = fields.Monetary(string='Importe pendiente')
    reconciliation_invoice_id = fields.Many2one('invoice_out', string='Factura', required=True, readonly=True)

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        for record in self:
            if not record.payment_method:
                record.journal = False
            elif record.journal not in record.payment_method.allowed_journals:
                record.journal = (
                    record.payment_method.default_journal
                    or record.payment_method.allowed_journals[:1]
                )

    def action_confirm(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_sales', 'werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Ventas o Caja para registrar pagos.',
        )
        if (
            self.env.user.has_group('werlen_repuestos_erp.group_sales')
            and not self.env.user.has_group('werlen_repuestos_erp.group_accountant')
            and self.reconciliation_invoice_id.seller != self.env.user
        ):
            raise UserError('Sólo puedes registrar pagos para tus propias ventas.')
        if self.amount <= 0:
            return display_warning_toast('Monto inválido', 'El monto debe ser mayor que 0.')
        if not self.payment_method or not self.journal:
            return display_warning_toast('Datos faltantes', 'Debe seleccionar método de pago y diario.')
        if self.reconciliation_invoice_id.client != self.payer:
            return display_warning_toast(
                'Pagador inválido',
                'El pagador debe coincidir con el cliente de la factura.',
            )
        self.env['payment_line'].sudo().create({
            'amount': self.amount,
            'is_outgoing': False,
            'payment_method': self.payment_method.id,
            'journal': self.journal.id,
            'confirmed': False,
            'reconciliation_invoice_id': self.reconciliation_invoice_id.id,
            'payer': self.payer.id,
            'payee': self.company_id.partner_id.id,
            'payment_origin_explanation': 'payment_for_invoice_out',
        })
        return {'type': 'ir.actions.act_window_close'}
