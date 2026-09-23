from odoo import fields, models


class WerlenUserRole(models.Model):
    _name = 'werlen.user.role'
    _description = 'Rol visible de usuario Werlen'
    _order = 'sequence, name'

    name = fields.Char(string='Rol', required=True, translate=True)
    code = fields.Char(string='Código', required=True, index=True)
    sequence = fields.Integer(default=10)
    group_id = fields.Many2one(
        comodel_name='res.groups',
        string='Grupo técnico',
        required=True,
        ondelete='restrict',
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('werlen_user_role_code_unique', 'UNIQUE(code)', 'El código del rol debe ser único.'),
        ('werlen_user_role_group_unique', 'UNIQUE(group_id)', 'Cada grupo técnico solo puede tener un rol visible.'),
    ]
