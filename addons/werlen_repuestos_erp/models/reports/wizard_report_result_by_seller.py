from odoo import models, fields


class WizardReportResultBySeller(models.TransientModel):
    _name = 'wizard_report_result_by_seller'
    _description = 'Resultados: Ventas por Vendedor'
    _order = 'balance desc'

    wizard_id = fields.Many2one(
        'wizard_report',
        string='Wizard',
        ondelete='cascade'
    )

    seller_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        required=True
    )

    amount_invoices = fields.Integer(
        string='Cant. Facturas'
    )

    amount_credit_notes = fields.Integer(
        string='Cant. Notas de Crédito'
    )

    total_sold = fields.Monetary(
        string='Importe total vendido',
        currency_field='currency_id'
    )

    total_credit = fields.Monetary(
        string='Importe total crédito',
        currency_field='currency_id'
    )

    balance = fields.Monetary(
        string='Balance',
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
