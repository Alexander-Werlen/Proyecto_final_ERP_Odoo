from odoo.tests import TransactionCase


class TestSupplierClaimSelection(TransactionCase):
    def test_claims_dashboard_groups_supplier_activity(self):
        result = self.env['supplier_claim'].get_claims_returns_dashboard_data()
        self.assertIn('suppliers', result)
        self.assertIsInstance(result['suppliers'], list)
