from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWerlenUserManagement(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_management = cls.env.ref('werlen_repuestos_erp.group_management')
        cls.role_sales = cls.env.ref('werlen_repuestos_erp.role_sales')
        cls.role_galvez = cls.env.ref('werlen_repuestos_erp.role_galvez')
        cls.manager = cls.env['res.users'].sudo().create({
            'name': 'Gestor de pruebas',
            'login': 'test_user_management_manager',
            'password': 'test-password',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_management.id])],
        })

    def test_create_user_assigns_roles_and_password(self):
        wizard = self.env['wizard.werlen.user.create'].with_user(self.manager).create({
            'name': 'Empleado de pruebas',
            'employee_number': '9901',
            'role_ids': [(6, 0, [self.role_sales.id, self.role_galvez.id])],
            'password': 'initial-password',
            'password_confirmation': 'initial-password',
        })
        wizard.action_create_user()
        user = self.env['res.users'].sudo().search([('login', '=', 'E9901')], limit=1)
        self.assertTrue(user)
        self.assertEqual(user.partner_id.unique_identifier, 'E9901')
        self.assertEqual(user.partner_id.name, 'Empleado de pruebas (E9901)')
        self.assertEqual(user.tz, 'America/Argentina/Buenos_Aires')
        self.assertTrue(user.has_group('werlen_repuestos_erp.group_sales'))
        self.assertTrue(user.has_group('werlen_repuestos_erp.group_galvez'))
        auth_info = user.with_user(user)._check_credentials(
            {'type': 'password', 'password': 'initial-password'},
            {'interactive': True},
        )
        self.assertEqual(auth_info['uid'], user.id)

    def test_role_edit_removes_unselected_group(self):
        user = self.env['res.users'].sudo().create({
            'name': 'Empleado editable',
            'login': 'E9902',
            'password': 'initial-password',
            'groups_id': [(6, 0, [self.group_user.id])],
        })
        user.with_user(self.manager).write({
            'role_ids': [(6, 0, [self.role_galvez.id])],
        })
        self.assertTrue(user.has_group('werlen_repuestos_erp.group_galvez'))
        self.assertFalse(user.has_group('werlen_repuestos_erp.group_sales'))

    def test_duplicate_and_protected_users_are_rejected(self):
        partner = self.env['res.partner'].sudo().create({
            'name': 'Empleado existente',
            'unique_identifier': 'E9903',
            'email': 'E9903',
        })
        self.env['res.users'].sudo().create({
            'name': 'Empleado existente',
            'login': 'E9903',
            'partner_id': partner.id,
            'password': 'initial-password',
            'groups_id': [(6, 0, [self.group_user.id])],
        })
        with self.assertRaises(ValidationError):
            self.env['wizard.werlen.user.create'].with_user(self.manager).create({
                'name': 'Empleado duplicado',
                'employee_number': 'E9903',
                'password': 'initial-password',
                'password_confirmation': 'initial-password',
            }).action_create_user()

        system_user = self.env['res.users'].with_user(self.manager).browse(
            self.env.ref('werlen_repuestos_erp.user_system_werlen').id
        )
        with self.assertRaises(AccessError):
            system_user.write({'active': False})
