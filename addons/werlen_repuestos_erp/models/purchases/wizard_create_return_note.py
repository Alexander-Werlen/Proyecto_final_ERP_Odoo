from odoo import fields, models

from ...utils.group_verification import ensure_user_in_groups


class WizardCreateReturnNote(models.TransientModel):
    _name = 'wizard_create_return_note'
    _description = 'Asistente para crear notas de devolución'

    supplier_id = fields.Many2one('res.partner', string='Proveedor', required=True,
                                  domain=[('is_supplier', '=', True)])
    carrier_id = fields.Many2one('res.partner', string='Transportista',
                                 domain=[('is_carrier', '=', True)])
    package_count = fields.Char(string='Cantidad de bultos', default='1 Bulto')
    observations = fields.Text(string='Observaciones')

    def action_create(self):
        self.ensure_one()
        ensure_user_in_groups(self.env.user, ['werlen_repuestos_erp.group_administration'],
                              error_message='No tiene permisos para crear notas de devolución.')
        note = self.env['return_note'].create({
            'supplier_id': self.supplier_id.id,
            'carrier_id': self.carrier_id.id or False,
            'package_count': self.package_count,
            'observations': self.observations,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nota de devolución',
            'res_model': 'return_note',
            'view_mode': 'form',
            'res_id': note.id,
            'target': 'current',
        }
