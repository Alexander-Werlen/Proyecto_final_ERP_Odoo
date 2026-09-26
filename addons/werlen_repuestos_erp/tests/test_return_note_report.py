from odoo import fields
from odoo.tests import TransactionCase


class TestReturnNoteReport(TransactionCase):
    def test_return_note_report_renders(self):
        supplier = self.env['res.partner'].create({'name': 'Proveedor de prueba', 'is_supplier': True})
        note = self.env['return_note'].create({
            'supplier_id': supplier.id,
            'date': fields.Date.today(),
            'package_count': '1 Bulto',
        })
        self.assertEqual(note.get_print_lines(), [])
        pdf, file_type = self.env['ir.actions.report']._render_qweb_pdf(
            'werlen_repuestos_erp.action_report_return_note', note.ids,
        )
        self.assertIn(file_type, ('pdf', 'html'))
        self.assertTrue(pdf)
