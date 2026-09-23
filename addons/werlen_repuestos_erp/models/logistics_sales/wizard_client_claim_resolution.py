from odoo import fields, models
from odoo.exceptions import UserError


class WizardClientClaimResolution(models.TransientModel):
    _name = 'wizard_client_claim_resolution'
    _description = 'Asistente para resolver o cancelar reclamos de cliente'

    claim_id = fields.Many2one('client_claim', string='Reclamo', required=True, readonly=True)
    target_state = fields.Selection([('resolved', 'Resuelto'), ('canceled', 'Cancelado')],
                                    string='Estado final', required=True, readonly=True)
    observations = fields.Text(string='Cómo se resolvió/canceló', required=True)

    def action_apply(self):
        self.ensure_one()
        if self.claim_id.state != 'valid' or not self.observations.strip():
            raise UserError('El reclamo debe estar Válido y requiere observaciones.')
        self.claim_id.with_context(workflow_transition=True).write({
            'state': self.target_state, 'resolution_observations': self.observations.strip(),
            'resolution_date': fields.Date.context_today(self.claim_id),
            'resolution_user_id': self.env.user.id,
        })
        self.claim_id._log_action('Resolución' if self.target_state == 'resolved' else 'Cancelación',
                                  self.observations.strip())
        return {'type': 'ir.actions.act_window_close'}
