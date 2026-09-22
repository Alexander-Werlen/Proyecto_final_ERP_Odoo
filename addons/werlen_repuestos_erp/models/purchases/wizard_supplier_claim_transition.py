from odoo import fields, models


class WizardSupplierClaimTransition(models.TransientModel):
    _name = 'wizard_supplier_claim_transition'
    _description = 'Asistente para cambiar el estado de un reclamo'

    claim_id = fields.Many2one('supplier_claim', string='Reclamo', required=True, readonly=True)
    action = fields.Selection([
        ('start', 'Iniciar gestión'),
        ('resolve', 'Resolver'),
        ('reject', 'Rechazar'),
        ('reopen', 'Reabrir'),
    ], string='Acción', required=True)
    observations = fields.Text(string='Observaciones')

    def action_apply(self):
        self.ensure_one()
        if self.observations:
            self.claim_id.sudo().write({'resolution_observations': self.observations})
        actions = {
            'start': self.claim_id.action_start_progress,
            'resolve': self.claim_id.action_resolve,
            'reject': self.claim_id.action_reject,
            'reopen': self.claim_id.action_reopen,
        }
        actions[self.action]()
        return {'type': 'ir.actions.act_window_close'}
