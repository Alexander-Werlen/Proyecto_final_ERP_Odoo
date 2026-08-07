from odoo import models, fields

class InvoiceType(models.Model):
    _name = 'invoice_type'
    _rec_name = 'invoice_type_id'
    _description = "Registro de: Tipo de factura"

    invoice_type_id = fields.Char(
        string='Tipo factura', 
        required=True
    )

    """ SQL Constraints """
    _sql_constraints = [

        # Identificador único del tipo de factura
        (
            'invoice_type_id_uniq',
            'unique(invoice_type_id)',
            'Ya existe un tipo de factura con este identificador.'
        ),

        # Required: invoice_type_id
        (
            'invoice_type_id_not_null',
            'CHECK(invoice_type_id IS NOT NULL)',
            'El tipo de factura es obligatorio.'
        ),
    ]
