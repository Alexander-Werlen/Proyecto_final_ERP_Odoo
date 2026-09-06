from odoo import api, fields, models


class WizardFulfillmentOrderVerificationPaymentLine(models.TransientModel):
    _name = 'wizard_fulfillment_order_verification_payment_line'
    _description = 'Ayudante para: Registrar pago a factura durante su verificación'

    wizard_fulfillment_order_verification_id = fields.Many2one(
        'wizard_fulfillment_order_verification',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    amount = fields.Monetary(string='Importe', required=True)
    payment_method = fields.Many2one('payment_method', string='Método de pago', required=True)
    journal = fields.Many2one('journal', string='Diario', required=True)

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
