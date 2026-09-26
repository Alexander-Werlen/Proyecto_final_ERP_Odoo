from odoo import fields
from odoo.tests import TransactionCase


class TestReceptionReport(TransactionCase):
    def test_reception_report_renders(self):
        supplier = self.env['res.partner'].create({'name': 'Proveedor de prueba', 'is_supplier': True})
        carrier = self.env['res.partner'].create({'name': 'Transportista de prueba', 'is_carrier': True})
        reception = self.env['reception'].create({
            'supplier_id': supplier.id,
            'carrier_id': carrier.id,
            'packages_description': '1 bulto',
            'reception_datetime': fields.Datetime.now(),
            'who_received_ids': [(6, 0, [self.env.user.id])],
        })
        self.assertIsInstance(reception.get_print_received_by(), str)
        pdf, file_type = self.env['ir.actions.report']._render_qweb_pdf(
            'werlen_repuestos_erp.action_report_reception', reception.ids,
        )
        self.assertIn(file_type, ('pdf', 'html'))
        self.assertTrue(pdf)
