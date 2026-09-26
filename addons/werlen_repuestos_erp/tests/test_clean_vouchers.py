from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestCleanVouchers(TransactionCase):
    def test_preview_requires_confirmation_for_execution(self):
        wizard = self.env['wizard.clean_vouchers'].create({
            'sales_point': '0001',
            'cutoff_date': fields.Date.today(),
            'confirmation_text': 'incorrecto',
        })
        with self.assertRaises(UserError):
            wizard._check_confirmation_text()
        wizard.confirmation_text = 'LIMPIAR'
        wizard._check_confirmation_text()
        self.assertTrue(wizard._compute_cutoff_datetime())
