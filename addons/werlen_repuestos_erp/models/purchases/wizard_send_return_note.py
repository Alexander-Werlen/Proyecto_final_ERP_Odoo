from odoo import fields, models


class WizardSendReturnNote(models.TransientModel):
    _name = 'wizard_send_return_note'
    _description = 'Asistente para enviar una nota de devolución'

    return_note_id = fields.Many2one('return_note', string='Nota de devolución', required=True, readonly=True)
    supplier_id = fields.Many2one(related='return_note_id.supplier_id', string='Proveedor', readonly=True)
    package_count = fields.Char(related='return_note_id.package_count', string='Cantidad de bultos', readonly=True)
    carrier_id = fields.Many2one(related='return_note_id.carrier_id', string='Transportista', readonly=True)
    observations = fields.Text(string='Observaciones')

    def action_send(self):
        self.ensure_one()
        if self.observations:
            self.return_note_id.sudo().write({'observations': self.observations})
        self.return_note_id.action_send()
        return {'type': 'ir.actions.act_window_close'}
