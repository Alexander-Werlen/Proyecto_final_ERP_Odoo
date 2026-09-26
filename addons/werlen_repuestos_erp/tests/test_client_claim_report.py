from odoo import fields
from odoo.tests import TransactionCase


class TestClientClaimReport(TransactionCase):
    def test_client_claim_report_renders(self):
        product = self.env['purchase.product'].create({
            'name': 'TEST-REPORT-CLAIM',
            'description': 'Producto de prueba',
        })
        claim = self.env['client_claim'].create({
            'claim_date': fields.Date.today(),
            'reason': 'Prueba de impresión',
            'product_brand': 'Marca',
            'product_id': product.id,
            'client_name': 'Cliente de prueba',
        })
        self.assertIn('name', claim.get_print_company_data())
        pdf, file_type = self.env['ir.actions.report']._render_qweb_pdf(
            'werlen_repuestos_erp.action_report_client_claim', claim.ids,
        )
        self.assertIn(file_type, ('pdf', 'html'))
        self.assertTrue(pdf)
