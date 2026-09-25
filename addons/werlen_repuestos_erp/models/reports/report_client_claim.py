from odoo import api, models


class ClientClaimReport(models.AbstractModel):
    _name = 'report.werlen_repuestos_erp.report_client_claim'
    _description = 'Reporte de reclamo de cliente'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['client_claim'].browse(docids)
        for claim in docs:
            claim._validate_printable_content()

        return {
            'doc_ids': docids,
            'doc_model': 'client_claim',
            'docs': docs,
        }
