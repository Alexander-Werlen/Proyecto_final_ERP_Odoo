from odoo import models, fields


class WizardReportResultByPreparer(models.TransientModel):
    _name = 'wizard_report_result_by_preparer'
    _description = 'Resultados: Tiempo de Preparación por Preparador'
    _order = 'in_range_count desc'

    wizard_id = fields.Many2one(
        'wizard_report',
        string='Wizard',
        ondelete='cascade'
    )

    preparer_id = fields.Many2one(
        'res.users',
        string='Preparador',
        required=True
    )

    total_invoices = fields.Integer(
        string='Cant. Facturas'
    )

    in_range_count = fields.Integer(
        string='Cant. en Rango'
    )

    avg_preparation_time = fields.Float(
        string='Tiempo Promedio (min)',
        digits=(10, 1)
    )

    under_5_min_count = fields.Integer(
        string='< 5 min'
    )

    over_4_hours_count = fields.Integer(
        string='> 4 horas'
    )
