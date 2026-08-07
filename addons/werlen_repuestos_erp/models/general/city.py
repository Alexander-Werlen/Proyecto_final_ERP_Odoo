from odoo import models, fields, api

class City(models.Model):
    _name = 'city'
    _rec_name = 'identifier'
    _description = "Registro de: Ciudad"

    identifier = fields.Char(
        string='Identificador', 
        store=True,
        compute='_compute_identifier',
        readonly=True
    )

    name = fields.Char(
        string='Nombre', 
        required=True,
    )

    state_id = fields.Many2one(
        'res.country.state', 
        string='Provincia', 
    )

    zip_code = fields.Char(
        string='Código Postal', 
        required=True
    )

    @api.depends('name', 'zip_code', 'state_id')
    def _compute_identifier(self):
        for record in self:
            if record.state_id:
                record.identifier = f"{record.name} - {record.zip_code} - {record.state_id.name}"
            else:
                record.identifier = f"{record.name if record.name else 'Nombre Desconocido'} - {record.zip_code if record.zip_code else 'Código Postal Desconocido'}"

    
    """ SQL Constraints """
    
    _sql_constraints = [

        # Required: name
        (
            'city_name_not_null',
            'CHECK(name IS NOT NULL)',
            'El nombre de la ciudad es obligatorio.'
        ),

        # Required: zip_code
        (
            'city_zip_code_not_null',
            'CHECK(zip_code IS NOT NULL)',
            'El código postal es obligatorio.'
        ),

        # Evitar ciudades duplicadas por nombre + provincia + código postal
        (
            'city_name_state_zip_uniq',
            'unique(name, state_id, zip_code)',
            'Ya existe una ciudad con el mismo nombre, provincia y código postal.'
        ),

    ]

