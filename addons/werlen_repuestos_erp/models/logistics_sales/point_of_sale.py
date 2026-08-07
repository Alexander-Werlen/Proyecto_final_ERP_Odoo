from odoo import models, fields

class PointOfSale(models.Model):
    _name = 'point_of_sale'
    _rec_name = 'name'
    _description = 'Registro de: Punto de venta'

    name = fields.Char(
        string='Punto de venta', 
        required=True
    )

    cellphone_required = fields.Boolean(
        string='Obligar anotar el teléfono del cliente', 
        default=False
    )

    """ SQL Constraints """
    _sql_constraints = [

        # Identificador único del punto de venta
        (
            'point_of_sale_name_uniq',
            'unique(name)',
            'Ya existe un punto de venta con este nombre.'
        ),

        # Required: name
        (
            'point_of_sale_name_not_null',
            'CHECK(name IS NOT NULL)',
            'El nombre del punto de venta es obligatorio.'
        ),
    ]