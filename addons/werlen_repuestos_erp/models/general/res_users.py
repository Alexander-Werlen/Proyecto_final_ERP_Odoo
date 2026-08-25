from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    default_journal_id = fields.Many2one(
        comodel_name='journal',
        string='Caja/Diario por defecto',
    )
