from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from ...enums.purchases.supplier_claim_state import SUPPLIER_CLAIM_STATE_ENUM
from ...enums.purchases.supplier_claim_type import SUPPLIER_CLAIM_TYPE_ENUM
from ...utils.group_verification import ensure_user_in_groups


CLAIM_MANAGE_GROUPS = [
    'werlen_repuestos_erp.group_administration',
]


class SupplierClaim(models.Model):
    _name = 'supplier_claim'
    _description = 'Reclamo a proveedor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'creation_date desc, id desc'

    name = fields.Char(string='Identificador', required=True, readonly=True,
                       index=True, copy=False, default='Nuevo')
    claim_type = fields.Selection(SUPPLIER_CLAIM_TYPE_ENUM, string='Tipo de reclamo',
                                  required=True, readonly=True, tracking=True)
    supplier_id = fields.Many2one('res.partner', string='Proveedor', required=True,
                                  tracking=True, domain=[('is_supplier', '=', True)])
    product_id = fields.Many2one('purchase.product', string='Producto', required=True,
                                 readonly=True, tracking=True)
    list_price = fields.Monetary(string='Precio de lista', currency_field='currency_id',
                                 readonly=True, tracking=True)
    observations = fields.Text(string='Observaciones', tracking=True)
    state = fields.Selection(SUPPLIER_CLAIM_STATE_ENUM, string='Estado', default='open',
                             required=True, readonly=True, index=True, tracking=True)
    purchase_invoice_id = fields.Many2one('purchase_invoice', string='Factura de compra',
                                          readonly=True, tracking=True)
    reception_id = fields.Many2one('reception', string='Ingreso de mercadería',
                                   readonly=True, tracking=True)
    client_claim_id = fields.Many2one('client_claim', string='Reclamo de cliente',
                                      readonly=True, tracking=True)
    return_line_ids = fields.One2many('return_line', 'claim_id', string='Líneas de devolución',
                                      readonly=True)
    active_return_line_id = fields.Many2one('return_line', string='Línea activa', readonly=True)
    who_created_id = fields.Many2one('res.users', string='Creado por',
                                     default=lambda self: self.env.user, readonly=True)
    resolution_observations = fields.Text(string='Descripción de resolución', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía',
                                 default=lambda self: self.env.user.company_id, readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    creation_date = fields.Datetime(string='Fecha de creación', default=fields.Datetime.now,
                                    required=True, readonly=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('supplier.claim')
        return super().create(vals_list)

    def _check_manage_permission(self):
        ensure_user_in_groups(self.env.user, CLAIM_MANAGE_GROUPS,
                              error_message='No tiene permisos para gestionar reclamos a proveedor.')

    def _log_action(self, action):
        self.ensure_one()
        timestamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        self.message_post(
            body=Markup(
                '<ul style="margin:0;padding-left:16px;">'
                f'<li><b>Acción:</b> {action}</li>'
                f'<li><b>Usuario:</b> {self.env.user.name}</li>'
                f'<li><b>Fecha:</b> {timestamp:%Y-%m-%d %H:%M:%S}</li>'
                '</ul>'
            ),
            message_type='comment', subtype_xmlid='mail.mt_note',
        )

    def action_start_progress(self):
        self.ensure_one()
        self._check_manage_permission()
        if self.state != 'open':
            raise UserError('Solo se puede iniciar la gestión desde un reclamo abierto.')
        self.sudo().write({'state': 'in_progress'})
        self._log_action('Inició la gestión del reclamo.')

    def action_resolve(self):
        self.ensure_one()
        self._check_manage_permission()
        if self.state not in ('open', 'in_progress'):
            raise UserError('Solo se puede resolver un reclamo abierto o en gestión.')
        self.sudo().write({'state': 'resolved'})
        self._log_action('Resolvió el reclamo.')

    def action_reject(self):
        self.ensure_one()
        self._check_manage_permission()
        if self.state not in ('open', 'in_progress'):
            raise UserError('Solo se puede rechazar un reclamo abierto o en gestión.')
        self.sudo().write({'state': 'rejected'})
        self._log_action('Rechazó el reclamo.')

    def action_reopen(self):
        self.ensure_one()
        self._check_manage_permission()
        if self.state not in ('resolved', 'rejected'):
            raise UserError('Solo se puede reabrir un reclamo resuelto o rechazado.')
        self.sudo().write({'state': 'open', 'resolution_observations': False})
        self._log_action('Reabrió el reclamo.')
