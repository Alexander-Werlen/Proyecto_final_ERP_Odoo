from odoo import models, fields

class ResPartner(models.Model):
    _inherit = "res.partner"

    city_relational_id = fields.Many2one(
        comodel_name="city",
        string="Ciudad",
        tracking=True
    )

    unique_identifier = fields.Char(
        string="Identificador",
        index=True,
        tracking=True
    )

    _sql_constraints = [
        (
            'unique_identifier_unique',
            'UNIQUE(unique_identifier)',
            'El identificador de contacto debe ser único para cada contacto.'
        ),
    ]
