from odoo import Command, SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError


USER_MANAGEMENT_GROUP = 'werlen_repuestos_erp.group_management'
SYSTEM_GROUP = 'werlen_repuestos_erp.group_system'
DEFAULT_USER_TIMEZONE = 'America/Argentina/Buenos_Aires'
MANAGED_ROLE_GROUPS = (
    'werlen_repuestos_erp.group_sales',
    'werlen_repuestos_erp.group_sales_meli',
    'werlen_repuestos_erp.group_manage_account_payments',
    'werlen_repuestos_erp.group_accountant',
    'werlen_repuestos_erp.group_reception',
    'werlen_repuestos_erp.group_reception_control',
    'werlen_repuestos_erp.group_administration',
    'werlen_repuestos_erp.group_preparation',
    'werlen_repuestos_erp.group_management',
    'werlen_repuestos_erp.group_galvez',
)


def normalize_employee_identifier(value):
    value = (value or '').strip().upper()
    if value.startswith('E'):
        value = value[1:]
    if not value.isdigit():
        raise ValidationError('El número de empleado debe contener solamente números.')
    return f'E{value}'


class ResUsers(models.Model):
    _inherit = 'res.users'

    employee_identifier = fields.Char(
        string='Número de empleado', related='partner_id.unique_identifier',
        readonly=True, search='_search_employee_identifier',
    )
    needs_completion = fields.Boolean(
        string='Pendiente de completar', compute='_compute_needs_completion',
        search='_search_needs_completion',
    )
    role_ids = fields.Many2many(
        comodel_name='werlen.user.role', string='Roles',
        compute='_compute_role_ids', inverse='_inverse_role_ids', compute_sudo=True,
    )

    @api.readonly
    def has_group(self, group_ext_id):
        result = super().has_group(group_ext_id)
        if group_ext_id != 'base.group_allow_export':
            return result
        return self.id == SUPERUSER_ID or self._has_group(USER_MANAGEMENT_GROUP) or self._has_group('base.group_erp_manager')

    @api.model
    def _search_employee_identifier(self, operator, value):
        return [('partner_id.unique_identifier', operator, value)]

    @api.depends('name', 'partner_id.unique_identifier')
    def _compute_needs_completion(self):
        for user in self:
            user.needs_completion = not user.partner_id.unique_identifier or (user.name or '').startswith('Falta Definir')

    @api.model
    def _search_needs_completion(self, operator, value):
        domain = ['|', ('name', 'ilike', 'Falta Definir'), ('partner_id.unique_identifier', '=', False)]
        return domain if operator in ('=', '==') and bool(value) else ['!'] + domain

    def _check_user_management_access(self):
        if self.env.su or self.env.user.has_group(USER_MANAGEMENT_GROUP):
            return
        raise AccessError('No tiene permisos para gestionar usuarios y sus roles.')

    def _check_managed_user_target(self):
        if self.env.su or self.env.user.has_group(SYSTEM_GROUP) or self.env.user.has_group('base.group_system'):
            return
        if self.filtered(lambda user: user.id == SUPERUSER_ID or user.has_group(SYSTEM_GROUP)):
            raise AccessError('Los usuarios del sistema no pueden modificarse desde esta pantalla.')

    def _role_ids_from_current_groups(self):
        roles = self.env['werlen.user.role'].sudo().search([('active', '=', True)])
        groups = set(self.groups_id.ids)
        role_by_code = {role.code: role for role in roles}
        ref = self.env.ref
        selected_codes = []
        if ref('werlen_repuestos_erp.group_management').id in groups:
            selected_codes.append('management')
        elif ref('werlen_repuestos_erp.group_administration').id in groups:
            selected_codes.append('administration')
        elif ref('werlen_repuestos_erp.group_accountant').id in groups:
            selected_codes.append('accountant')
        elif ref('werlen_repuestos_erp.group_manage_account_payments').id in groups:
            selected_codes.append('account_income')
        if 'management' not in selected_codes and 'administration' not in selected_codes:
            if ref('werlen_repuestos_erp.group_reception_control').id in groups:
                selected_codes.append('reception_control')
            if ref('werlen_repuestos_erp.group_reception').id in groups:
                selected_codes.append('reception')
            if ref('werlen_repuestos_erp.group_preparation').id in groups:
                selected_codes.append('preparation')
        if ref('werlen_repuestos_erp.group_sales_meli').id in groups:
            selected_codes.append('sales_meli')
        elif ref('werlen_repuestos_erp.group_sales').id in groups:
            selected_codes.append('sales')
        if ref('werlen_repuestos_erp.group_galvez').id in groups:
            selected_codes.append('galvez')
        return roles.browse([role_by_code[code].id for code in selected_codes if code in role_by_code])

    @api.depends('groups_id')
    def _compute_role_ids(self):
        for user in self:
            user.role_ids = [Command.set(user._role_ids_from_current_groups().ids)]

    def _inverse_role_ids(self):
        self._check_user_management_access()
        self._check_managed_user_target()
        managed_group_ids = {self.env.ref(xmlid).id for xmlid in MANAGED_ROLE_GROUPS}
        base_user_group_id = self.env.ref('base.group_user').id
        for user in self:
            selected_group_ids = set(user.role_ids.mapped('group_id').ids)
            selected_group_ids.add(base_user_group_id)
            current_group_ids = set(user.sudo().groups_id.ids)
            commands = [
                Command.unlink(group_id)
                for group_id in managed_group_ids
                if group_id in current_group_ids and group_id not in selected_group_ids
            ] + [
                Command.link(group_id)
                for group_id in selected_group_ids
                if group_id not in current_group_ids
            ]
            if commands:
                user.sudo().write({'groups_id': commands})

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.has_group(USER_MANAGEMENT_GROUP):
            raise AccessError('No tiene permisos para crear usuarios.')
        for vals in vals_list:
            vals.setdefault('tz', DEFAULT_USER_TIMEZONE)
        return super().create(vals_list)

    def write(self, vals):
        if 'employee_identifier' in vals:
            raise ValidationError('El número de empleado no puede modificarse una vez creado.')
        if not self.env.su and self.env.user.has_group(USER_MANAGEMENT_GROUP):
            self._check_managed_user_target()
        return super().write(vals)

    def action_open_new_password(self):
        self.ensure_one()
        self._check_user_management_access()
        self._check_managed_user_target()
        return {
            'type': 'ir.actions.act_window', 'name': 'Cambiar contraseña',
            'res_model': 'wizard.werlen.user.password', 'view_mode': 'form',
            'target': 'new', 'context': {'default_user_id': self.id},
        }

    default_journal_id = fields.Many2one(
        comodel_name='journal',
        string='Caja/Diario por defecto',
    )

    @api.model
    def ensure_default_admin_access(self):
        if not self.env.su:
            raise AccessError('La configuración inicial sólo puede ejecutarse desde el sistema.')
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        if not admin:
            return False

        groups = (
            self.env.ref('werlen_repuestos_erp.group_management', raise_if_not_found=False),
            self.env.ref('werlen_repuestos_erp.group_system', raise_if_not_found=False),
        )
        values = {
            'groups_id': [(4, group.id) for group in groups if group],
        }
        default_journal = self.env.ref(
            'werlen_repuestos_erp.journal_caja_1',
            raise_if_not_found=False,
        )
        if default_journal and not admin.default_journal_id:
            values['default_journal_id'] = default_journal.id
        admin.sudo().write(values)
        return True
