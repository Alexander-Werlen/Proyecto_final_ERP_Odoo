from odoo import api, fields, models
from odoo.exceptions import UserError

from ...enums.purchases.return_line_state import RETURN_LINE_STATE_ENUM


class ReturnLine(models.Model):
    _name = 'return_line'
    _description = 'Línea de devolución a proveedor'
    _rec_name = 'display_name'
    _order = 'id desc'

    return_note_id = fields.Many2one('return_note', string='Nota de devolución', required=True,
                                     readonly=True, ondelete='cascade')
    claim_id = fields.Many2one('supplier_claim', string='Reclamo de origen', required=True,
                               readonly=True, ondelete='restrict')
    product_code = fields.Char(string='Código de producto')
    product_description = fields.Text(string='Descripción del producto')
    reason = fields.Char(string='Motivo de devolución')
    quantity = fields.Integer(string='Cantidad', default=1)
    state = fields.Selection(RETURN_LINE_STATE_ENUM, string='Estado', default='draft',
                             required=True, readonly=True, index=True)
    observations = fields.Char(string='Observaciones')
    resolution_date = fields.Date(string='Fecha de resolución', readonly=True)
    display_name = fields.Char(string='Identificador', compute='_compute_display_name', store=True)

    @api.depends('return_note_id.name', 'claim_id.name')
    def _compute_display_name(self):
        for line in self:
            line.display_name = f'{line.return_note_id.name or "?"} / {line.claim_id.name or "?"}'

    def action_delete_line(self):
        for line in self:
            if line.return_note_id.state != 'draft':
                raise UserError('Solo se pueden eliminar líneas de una nota en borrador.')
            if line.claim_id.active_return_line_id == line:
                line.claim_id.sudo().write({'active_return_line_id': False})
            line.unlink()
