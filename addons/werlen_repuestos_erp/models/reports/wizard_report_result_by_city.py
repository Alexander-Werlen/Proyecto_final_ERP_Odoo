from odoo import models, fields


class WizardReportResultByCity(models.TransientModel):
    _name = 'wizard_report_result_by_city'
    _description = 'Resultados: Ventas por Ciudad'
    _order = 'total_invoiced desc'

    wizard_id = fields.Many2one(
        'wizard_report',
        string='Wizard',
        ondelete='cascade'
    )

    city_id = fields.Many2one(
        'city',
        string='Ciudad',
        required=True
    )

    invoice_count = fields.Integer(
        string='Cant. Facturas'
    )

    total_invoiced = fields.Monetary(
        string='Importe Facturado',
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
