from odoo import api, models


class ReturnNoteReport(models.AbstractModel):
    _name = 'report.werlen_repuestos_erp.report_return_note'
    _description = 'Reporte de nota de devolución'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['return_note'].browse(docids)
        for note in docs:
            note._validate_printable_content()

        return {
            'doc_ids': docids,
            'doc_model': 'return_note',
            'docs': docs,
        }
