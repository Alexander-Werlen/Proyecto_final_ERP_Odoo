from odoo import api, models


class ReceptionReport(models.AbstractModel):
    _name = 'report.werlen_repuestos_erp.report_reception'
    _description = 'Reporte de ingreso de mercadería'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['reception'].browse(docids)
        for reception in docs:
            reception._validate_printable_content()

        return {
            'doc_ids': docids,
            'doc_model': 'reception',
            'docs': docs,
        }
