from odoo import models, fields


class WizardReportResultByPaymentMethod(models.TransientModel):
    _name = 'wizard_report_result_by_payment_method'
    _description = 'Resultados: Ventas por Método de Pago'
    _order = 'total_invoiced desc'

    wizard_id = fields.Many2one(
        'wizard_report',
        string='Wizard',
        ondelete='cascade'
    )

    payment_method_id = fields.Many2one(
        'payment_method',
        string='Método de Pago',
        required=True
    )

    invoice_count = fields.Integer(
        string='Cant. Facturas'
    )

    total_invoiced = fields.Monetary(
        string='Importe Facturado',
        currency_field='currency_id'
    )

    is_account_move = fields.Boolean(
        string='Cuenta Corriente',
        related='payment_method_id.is_account_payment_method',
        store=True,
        readonly=True,
    )

    cash_closing_category_id = fields.Many2one(
        'cash_closing_category',
        string='Categoría de Cierre',
        related='payment_method_id.cash_closing_category_id',
        store=True,
        readonly=True,
    )

    percentage_of_total = fields.Float(
        string='% del Total',
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
