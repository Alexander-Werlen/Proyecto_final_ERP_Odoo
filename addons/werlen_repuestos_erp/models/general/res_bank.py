from odoo import fields, models


class ResBank(models.Model):
    _inherit = 'res.bank'

    city_id = fields.Many2one(
        comodel_name='city',
        string='Ciudad',
    )
