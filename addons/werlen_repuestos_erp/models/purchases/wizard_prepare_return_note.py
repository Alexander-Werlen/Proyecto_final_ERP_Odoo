from odoo import fields, models


class WizardPrepareReturnNote(models.TransientModel):
    _name = 'wizard_prepare_return_note'
    _description = 'Asistente para preparar una nota de devolución'

    return_note_id = fields.Many2one('return_note', string='Nota de devolución', required=True, readonly=True)
    observations = fields.Text(string='Observaciones')

    def action_prepare(self):
        self.ensure_one()
        if self.observations:
            self.return_note_id.sudo().write({'observations': self.observations})
        self.return_note_id.action_prepare()
        return {'type': 'ir.actions.act_window_close'}
