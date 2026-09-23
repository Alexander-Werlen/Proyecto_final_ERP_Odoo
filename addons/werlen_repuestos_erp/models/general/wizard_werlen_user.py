from odoo import fields, models
from odoo.exceptions import ValidationError

from .res_users import normalize_employee_identifier


class WizardWerlenUserCreate(models.TransientModel):
    _name = 'wizard.werlen.user.create'
    _description = 'Crear usuario Werlen'

    name = fields.Char(string='Nombre', required=True)
    employee_number = fields.Char(string='Número de empleado', required=True)
    role_ids = fields.Many2many(
        comodel_name='werlen.user.role', string='Roles',
        domain=[('active', '=', True)],
    )
    default_journal_id = fields.Many2one('journal', string='Caja/Diario por defecto')
    password = fields.Char(string='Contraseña inicial', required=True)
    password_confirmation = fields.Char(string='Confirmar contraseña', required=True)

    def action_create_user(self):
        self.ensure_one()
        users = self.env['res.users']
        users._check_user_management_access()
        if self.password != self.password_confirmation:
            raise ValidationError('La contraseña y su confirmación deben coincidir.')

        identifier = normalize_employee_identifier(self.employee_number)
        user_name = (self.name or '').strip()
        if not user_name:
            raise ValidationError('El nombre del usuario es obligatorio.')
        contact_name = f'{user_name} ({identifier})'
        partner_model = self.env['res.partner'].sudo()
        partner = partner_model.search([('unique_identifier', '=', identifier)], limit=1)
        existing_user = users.sudo().with_context(active_test=False).search([
            '|', ('login', '=', identifier),
            ('partner_id.unique_identifier', '=', identifier),
        ], limit=1)
        if existing_user:
            status = 'inactivo' if not existing_user.active else 'activo'
            raise ValidationError(
                f'Ya existe un usuario {status} para el identificador {identifier}.'
            )

        if partner:
            partner.write({'name': contact_name, 'email': identifier})
        else:
            partner = partner_model.create({
                'name': contact_name,
                'unique_identifier': identifier,
                'email': identifier,
            })

        user = users.sudo().with_context(no_reset_password=True).create({
            'name': user_name,
            'login': identifier,
            'partner_id': partner.id,
            'notification_type': 'inbox',
            'default_journal_id': self.default_journal_id.id or False,
        })
        partner.sudo().write({'name': contact_name})
        user._set_encrypted_password(user.id, user._crypt_context().hash(self.password))
        user.with_context(skip_user_management_access=True).sudo().write({
            'role_ids': [(6, 0, self.role_ids.ids)],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Usuario creado',
            'res_model': 'res.users',
            'view_mode': 'form',
            'view_id': self.env.ref('werlen_repuestos_erp.werlen_user_management_form_view').id,
            'res_id': user.id,
            'target': 'current',
        }


class WizardWerlenUserPassword(models.TransientModel):
    _name = 'wizard.werlen.user.password'
    _description = 'Cambiar contraseña de usuario Werlen'

    user_id = fields.Many2one('res.users', string='Usuario', required=True, readonly=True)
    password = fields.Char(string='Nueva contraseña', required=True)
    password_confirmation = fields.Char(string='Confirmar contraseña', required=True)

    def action_change_password(self):
        self.ensure_one()
        self.env['res.users']._check_user_management_access()
        self.user_id._check_managed_user_target()
        if self.password != self.password_confirmation:
            raise ValidationError('La contraseña y su confirmación deben coincidir.')
        user = self.user_id.sudo()
        user._set_encrypted_password(user.id, user._crypt_context().hash(self.password))
        return {'type': 'ir.actions.act_window_close'}
