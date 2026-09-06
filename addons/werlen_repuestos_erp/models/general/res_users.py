from odoo import api, fields, models
from odoo.exceptions import AccessError


class ResUsers(models.Model):
    _inherit = 'res.users'

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
