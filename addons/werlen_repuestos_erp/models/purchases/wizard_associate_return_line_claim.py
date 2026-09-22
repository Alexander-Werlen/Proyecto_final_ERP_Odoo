from odoo import fields, models
from odoo.exceptions import UserError

from ...utils.group_verification import ensure_user_in_groups


class WizardAssociateReturnLineClaim(models.TransientModel):
    _name = 'wizard_associate_return_line_claim'
    _description = 'Asistente para asociar un reclamo a una nota de devolución'

    return_note_id = fields.Many2one('return_note', string='Nota de devolución', required=True, readonly=True)
    claim_id = fields.Many2one('supplier_claim', string='Reclamo', required=True,
                               domain=[('state', 'in', ('open', 'in_progress'))])
    product_code = fields.Char(string='Código de producto')
    product_description = fields.Text(string='Descripción del producto')
    reason = fields.Char(string='Motivo de devolución')
    quantity = fields.Integer(string='Cantidad', default=1, required=True)

    def action_associate(self):
        self.ensure_one()
        ensure_user_in_groups(self.env.user, ['werlen_repuestos_erp.group_administration'],
                              error_message='No tiene permisos para asociar reclamos a devoluciones.')
        if self.return_note_id.state != 'draft':
            raise UserError('Solo se pueden asociar reclamos a una nota en borrador.')
        if self.claim_id.active_return_line_id:
            raise UserError('El reclamo ya está asociado a una línea de devolución.')
        line = self.env['return_line'].create({
            'return_note_id': self.return_note_id.id,
            'claim_id': self.claim_id.id,
            'product_code': self.product_code or self.claim_id.product_id.name,
            'product_description': self.product_description or self.claim_id.product_id.description,
            'reason': self.reason or dict(self.claim_id._fields['claim_type'].selection).get(self.claim_id.claim_type),
            'quantity': self.quantity,
        })
        self.claim_id.sudo().write({'active_return_line_id': line.id})
        return {'type': 'ir.actions.act_window_close'}
