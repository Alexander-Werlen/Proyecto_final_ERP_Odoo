from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from ...enums.logistics_sales.client_claim_state import CLIENT_CLAIM_STATE_ENUM
from ...utils.group_verification import ensure_user_in_groups


class ClientClaim(models.Model):
    _name = 'client_claim'
    _description = 'Reclamo de cliente'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'claim_date desc, id desc'

    name = fields.Char(string='Número de reclamo', required=True, readonly=True,
                       index=True, copy=False, default='Nuevo', tracking=True)
    claim_date = fields.Date(string='Fecha de reclamo', required=True,
                             default=fields.Date.context_today, tracking=True)
    reason = fields.Text(string='Motivo', required=True, tracking=True)
    product_brand = fields.Char(string='Marca', required=True, tracking=True)
    product_id = fields.Many2one('purchase.product', string='Código del producto',
                                 required=True, tracking=True)
    vehicle_description = fields.Char(string='Vehículo', tracking=True)
    sale_fulfillment_order_id = fields.Many2one('sale_fulfillment_order', string='Factura', tracking=True)
    sale_invoice_date = fields.Datetime(related='sale_fulfillment_order_id.invoice_id.date',
                                        string='Fecha de la factura', store=True)
    client_name = fields.Char(string='Nombre cliente', required=True, tracking=True)
    client_address = fields.Char(string='Dirección', tracking=True)
    client_phone = fields.Char(string='Teléfono', tracking=True)
    state = fields.Selection(CLIENT_CLAIM_STATE_ENUM, string='Estado', default='draft',
                             required=True, index=True, tracking=True)
    resolution_observations = fields.Text(string='Observaciones de cierre', tracking=True)
    resolution_date = fields.Date(string='Fecha de cierre', tracking=True)
    resolution_user_id = fields.Many2one('res.users', string='Resuelto/cancelado por', readonly=True)
    supplier_claim_id = fields.Many2one('supplier_claim', string='Reclamo a proveedor asociado',
                                       tracking=True)
    supplier_claim_state = fields.Selection(related='supplier_claim_id.state',
                                            string='Estado del reclamo a proveedor', store=True)
    who_created_id = fields.Many2one('res.users', string='Registrado por',
                                     default=lambda self: self.env.user, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('client.claim')
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get('workflow_transition'):
            return super().write(vals)
        protected = {'state', 'resolution_observations', 'resolution_date', 'resolution_user_id'}
        if protected.intersection(vals):
            raise UserError('Los cambios de estado solo pueden realizarse mediante las acciones del flujo.')
        if self.filtered(lambda claim: claim.state != 'draft') and vals:
            if set(vals) != {'supplier_claim_id'} or self.filtered(lambda claim: claim.state != 'valid'):
                raise UserError('Solo se pueden modificar reclamos en Borrador.')
            ensure_user_in_groups(self.env.user, ['werlen_repuestos_erp.group_administration'])
        return super().write(vals)

    def _check_admin(self):
        ensure_user_in_groups(self.env.user, ['werlen_repuestos_erp.group_administration'],
                              error_message='No tiene permisos para gestionar reclamos de cliente.')

    def _log_action(self, action, description):
        self.ensure_one()
        timestamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        self.message_post(body=Markup(
            '<ul style="margin:0;padding-left:16px;">'
            f'<li><b>Acción:</b> {action}</li><li><b>Descripción:</b> {description}</li>'
            f'<li><b>Usuario:</b> {self.env.user.name}</li><li><b>Fecha:</b> {timestamp:%Y-%m-%d %H:%M:%S}</li>'
            '</ul>'
        ), message_type='comment', subtype_xmlid='mail.mt_note')

    def action_validate(self):
        self._check_admin()
        if any(claim.state != 'draft' for claim in self):
            raise UserError('Solo se pueden validar reclamos en Borrador.')
        for claim in self:
            claim.with_context(workflow_transition=True).write({'state': 'valid'})
            claim._log_action('Validación', 'El reclamo fue marcado como válido.')

    def action_revert_to_draft(self):
        self.ensure_one(); self._check_admin()
        if self.state != 'valid':
            raise UserError('Solo se puede volver a Borrador desde Válido.')
        self.with_context(workflow_transition=True).write({'state': 'draft'})
        self._log_action('Retroceso de estado', 'El reclamo volvió a Borrador.')

    def _open_resolution_wizard(self, target_state):
        self.ensure_one(); self._check_admin()
        if self.state != 'valid':
            raise UserError('Solo se pueden resolver o cancelar reclamos Válidos.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Resolver reclamo' if target_state == 'resolved' else 'Cancelar reclamo',
            'res_model': 'wizard_client_claim_resolution', 'view_mode': 'form',
            'view_id': self.env.ref('werlen_repuestos_erp.wizard_client_claim_resolution_form_view').id,
            'target': 'new',
            'context': {'default_claim_id': self.id, 'default_target_state': target_state},
        }

    def action_open_resolve_wizard(self):
        return self._open_resolution_wizard('resolved')

    def action_open_cancel_wizard(self):
        return self._open_resolution_wizard('canceled')

    def action_open_wizard_create_supplier_claim(self):
        self.ensure_one(); self._check_admin()
        if self.supplier_claim_id:
            raise UserError('El reclamo de cliente ya tiene un reclamo a proveedor asociado.')
        return {
            'type': 'ir.actions.act_window', 'name': 'Crear reclamo a proveedor',
            'res_model': 'wizard_create_supplier_claim', 'view_mode': 'form',
            'view_id': self.env.ref('werlen_repuestos_erp.wizard_create_supplier_claim_form_view').id,
            'target': 'new',
            'context': {'default_client_claim_id': self.id, 'default_claim_type': 'defective',
                        'default_product_id': self.product_id.id, 'default_quantity': 1},
        }
