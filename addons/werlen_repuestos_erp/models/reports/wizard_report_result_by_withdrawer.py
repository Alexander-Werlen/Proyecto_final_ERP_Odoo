from odoo import models, fields


class WizardReportResultByWithdrawer(models.TransientModel):
    _name = 'wizard_report_result_by_withdrawer'
    _description = 'Resultados: Ventas por Quien Retira'
    _order = 'total_cost desc'

    wizard_id = fields.Many2one(
        'wizard_report',
        string='Wizard',
        ondelete='cascade'
    )

    withdrawer_id = fields.Many2one(
        'res.partner',
        string='Quien Retira',
        required=True
    )

    order_count = fields.Integer(
        string='Cant. Ordenes'
    )

    total_cost = fields.Monetary(
        string='Importe Total',
        currency_field='currency_id'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        default=lambda self: self.env.user.company_id,
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id',
    )
