from odoo import models, fields


class WizardReportResultByClient(models.TransientModel):
    _name = 'wizard_report_result_by_client'
    _description = 'Resultados: Ventas por Cliente'
    _order = 'net_amount desc'

    wizard_id = fields.Many2one(
        'wizard_report',
        string='Wizard',
        ondelete='cascade'
    )

    client_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True
    )

    total_invoiced = fields.Monetary(
        string='Importe Facturas',
        currency_field='currency_id'
    )

    total_credit_notes = fields.Monetary(
        string='Importe Notas de Crédito',
        currency_field='currency_id'
    )

    net_amount = fields.Monetary(
        string='Importe Neto',
        currency_field='currency_id'
    )

    invoice_count = fields.Integer(
        string='Cant. Facturas'
    )

    credit_note_count = fields.Integer(
        string='Cant. Notas de Crédito'
    )

    account_percentage = fields.Float(
        string='% en Cta. Cte.',
        digits=(5, 2)
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
