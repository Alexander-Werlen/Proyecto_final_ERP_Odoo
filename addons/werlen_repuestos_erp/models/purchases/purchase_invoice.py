from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError

from ...enums.purchases.purchase_invoice_state import PURCHASE_INVOICE_STATE_ENUM
from ...utils.group_verification import ensure_user_in_groups


PURCHASE_INVOICE_CONTROL_GROUPS = [
    'werlen_repuestos_erp.group_reception_control',
    'werlen_repuestos_erp.group_administration',
]


class PurchaseInvoice(models.Model):
    _name = 'purchase_invoice'
    _description = 'Factura de compra'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string='Número', required=True, index=True, tracking=True)
    supplier_id = fields.Many2one(
        'res.partner', string='Proveedor', required=True, index=True,
        tracking=True, domain=[('is_supplier', '=', True)],
    )
    state = fields.Selection(
        PURCHASE_INVOICE_STATE_ENUM,
        string='Estado de revisión',
        default='pending_review',
        required=True,
        readonly=True,
        index=True,
        tracking=True,
    )
    observations = fields.Text(string='Observaciones', tracking=True)
    controlled_datetime_start = fields.Datetime(string='Inicio de control', readonly=True)
    controlled_datetime_end = fields.Datetime(string='Fin de control', readonly=True)
    who_controlled_ids = fields.Many2many(
        'res.users',
        'purchase_invoice_who_controlled_rel',
        'purchase_invoice_id',
        'user_id',
        string='Controlado por',
        tracking=True,
    )
    reception_ids = fields.Many2many(
        'reception',
        'reception_purchase_invoice_rel',
        'purchase_invoice_id',
        'reception_id',
        string='Ingresos',
        tracking=True,
    )

    _sql_constraints = [
        (
            'purchase_invoice_name_supplier_unique',
            'UNIQUE(name, supplier_id)',
            'Ya existe una factura de compra con ese número para el mismo proveedor.',
        ),
    ]

    def _check_control_permission(self):
        ensure_user_in_groups(
            self.env.user,
            PURCHASE_INVOICE_CONTROL_GROUPS,
            error_message='No tiene permisos para controlar facturas de compra.',
        )

    def _log_action(self, message):
        self.ensure_one()
        timestamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        self.message_post(
            body=Markup(
                '<ul style="margin:0;padding-left:16px;">'
                f'<li><b>Acción:</b> {message}</li>'
                f'<li><b>Usuario:</b> {self.env.user.name}</li>'
                f'<li><b>Fecha:</b> {timestamp:%Y-%m-%d %H:%M:%S}</li>'
                '</ul>'
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

    def action_move_to_pending_review(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'pending_delivery':
            raise UserError('Solo se puede marcar como recibida una factura en entrega pendiente.')
        self.sudo().write({'state': 'pending_review'})
        self._log_action('Marcó la factura como recibida.')

    def action_start_review(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'pending_review':
            raise UserError('Solo se puede iniciar la revisión desde revisión pendiente.')
        self.sudo().write({
            'state': 'in_review',
            'controlled_datetime_start': fields.Datetime.now(),
            'who_controlled_ids': [(4, self.env.user.id)],
        })
        self._log_action('Inició la revisión de la factura.')

    def action_finish_review(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'in_review':
            raise UserError('Solo se puede finalizar la revisión desde en revisión.')
        self.sudo().write({
            'state': 'reviewed',
            'controlled_datetime_end': fields.Datetime.now(),
            'who_controlled_ids': [(4, self.env.user.id)],
        })
        self._log_action('Finalizó la revisión de la factura.')

    def action_revert_to_pending_delivery(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'pending_review':
            raise UserError('Solo se puede volver a entrega pendiente desde revisión pendiente.')
        self.sudo().write({'state': 'pending_delivery'})
        self._log_action('Volvió la factura a entrega pendiente.')

    def action_cancel_review(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'in_review':
            raise UserError('Solo se puede cancelar la revisión desde en revisión.')
        self.sudo().write({
            'state': 'pending_review',
            'controlled_datetime_start': False,
        })
        self._log_action('Canceló la revisión de la factura.')

    def action_reopen_review(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'reviewed':
            raise UserError('Solo se puede reabrir una factura revisada.')
        self.sudo().write({
            'state': 'in_review',
            'controlled_datetime_end': False,
        })
        self._log_action('Reabrió la revisión de la factura.')
