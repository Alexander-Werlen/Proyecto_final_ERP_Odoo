from odoo import api, fields, models


class WizardCloseCashSessionLine(models.TransientModel):
    _name = 'wizard_close_cash_session_line'
    _description = 'Línea de wizard de cierre de caja'

    wizard_id = fields.Many2one(
        'wizard_close_cash_session',
        required=True,
        ondelete='cascade',
    )
    cash_session_line_id = fields.Many2one(
        'cash_session_line',
        required=True,
        readonly=True,
    )
    category_id = fields.Many2one(
        related='cash_session_line_id.category_id',
        string='Categoría',
        readonly=True,
    )
    opening_balance = fields.Monetary(related='cash_session_line_id.opening_balance', readonly=True)
    movements_amount = fields.Monetary(related='cash_session_line_id.movements_amount', readonly=True)
    theoretical_balance = fields.Monetary(related='cash_session_line_id.theoretical_balance', readonly=True)
    payment_count = fields.Integer(related='cash_session_line_id.payment_count', readonly=True)
    counted_balance = fields.Monetary(string='Saldo final', required=True, default=0.0)
    difference = fields.Monetary(string='Diferencia', compute='_compute_difference')
    currency_id = fields.Many2one(related='wizard_id.currency_id', readonly=True)

    @api.depends('theoretical_balance', 'counted_balance')
    def _compute_difference(self):
        for record in self:
            record.difference = record.counted_balance - record.theoretical_balance
