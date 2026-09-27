from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from ...enums.reception.reception_state import RECEPTION_STATE_ENUM
from ...utils.group_verification import ensure_user_in_groups


RECEPTION_CONTROL_GROUPS = [
    'werlen_repuestos_erp.group_reception_control',
    'werlen_repuestos_erp.group_administration',
]


class Reception(models.Model):
    _name = 'reception'
    _description = 'Ingreso de mercadería'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'reception_datetime desc, id desc'

    name = fields.Char(
        string='Identificador',
        required=True,
        readonly=True,
        index=True,
        copy=False,
        default='Nuevo',
    )
    reception_datetime = fields.Datetime(
        string='Fecha y hora de recepción',
        required=True,
        readonly=True,
        index=True,
        tracking=True,
        default=fields.Datetime.now,
    )
    supplier_id = fields.Many2one(
        'res.partner',
        string='Proveedor',
        required=True,
        readonly=True,
        index=True,
        tracking=True,
        domain=[('is_supplier', '=', True)],
    )
    carrier_id = fields.Many2one(
        'res.partner',
        string='Transportista',
        required=True,
        readonly=True,
        index=True,
        tracking=True,
        domain=[('is_carrier', '=', True)],
    )
    packages_description = fields.Char(
        string='Bultos',
        required=True,
        tracking=True,
        help='Descripción de la cantidad y tipo de bultos o pallets recibidos.',
    )
    remito_number = fields.Char(string='Número de remito', tracking=True)
    observations = fields.Text(string='Observaciones', tracking=True)
    state = fields.Selection(
        RECEPTION_STATE_ENUM,
        string='Estado',
        default='pending_review',
        required=True,
        readonly=True,
        index=True,
        tracking=True,
    )
    controlled_datetime_start = fields.Datetime(
        string='Inicio de control', readonly=True,
    )
    controlled_datetime_end = fields.Datetime(
        string='Fin de control', readonly=True,
    )
    who_received_ids = fields.Many2many(
        'res.users',
        'reception_who_received_rel',
        'reception_id',
        'user_id',
        string='Empleados que recibieron',
        required=True,
        readonly=True,
        tracking=True,
    )
    purchase_invoice_ids = fields.Many2many(
        'purchase_invoice',
        'reception_purchase_invoice_rel',
        'reception_id',
        'purchase_invoice_id',
        string='Facturas de compra',
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('reception')
        return super().create(vals_list)

    def _check_control_permission(self):
        ensure_user_in_groups(
            self.env.user,
            RECEPTION_CONTROL_GROUPS,
            error_message='No tiene permisos para controlar ingresos de mercadería.',
        )

    def _log_action(self, message):
        self.ensure_one()
        timestamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        body = Markup(
            '<ul style="margin:0;padding-left:16px;">'
            f'<li><b>Acción:</b> {message}</li>'
            f'<li><b>Usuario:</b> {self.env.user.name}</li>'
            f'<li><b>Fecha:</b> {timestamp:%Y-%m-%d %H:%M:%S}</li>'
            '</ul>'
        )
        self.message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

    def action_start_review(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'pending_review':
            raise UserError('Solo se puede iniciar la revisión desde revisión pendiente.')
        self.sudo().write({
            'state': 'in_review',
            'controlled_datetime_start': fields.Datetime.now(),
        })
        self._log_action('Inició la revisión del ingreso.')

    def action_finish_review(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'in_review':
            raise UserError('Solo se puede finalizar la revisión desde en revisión.')
        if not self.purchase_invoice_ids:
            raise UserError('No se puede finalizar el ingreso sin facturas de compra asociadas.')
        not_reviewed = self.purchase_invoice_ids.filtered(
            lambda invoice: invoice.state not in ('reviewed', 'pending_delivery')
        )
        if not_reviewed:
            raise UserError(
                'No se puede finalizar el ingreso: hay facturas de compra sin revisar: '
                + ', '.join(not_reviewed.mapped('name'))
            )
        self.sudo().write({
            'state': 'reviewed',
            'controlled_datetime_end': fields.Datetime.now(),
        })
        self._log_action('Finalizó la revisión del ingreso.')

    def action_cancel_review(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'in_review':
            raise UserError('Solo se puede cancelar la revisión desde en revisión.')
        self.sudo().write({
            'state': 'pending_review',
            'controlled_datetime_start': False,
            'controlled_datetime_end': False,
        })
        self._log_action('Canceló la revisión del ingreso.')

    def action_reopen_review(self):
        self.ensure_one()
        self._check_control_permission()
        if self.state != 'reviewed':
            raise UserError('Solo se puede reabrir un ingreso revisado.')
        self.sudo().write({
            'state': 'in_review',
            'controlled_datetime_end': False,
        })
        self._log_action('Reabrió la revisión del ingreso.')

    @api.model
    def get_reception_dashboard_data(self):
        max_boxes = 12
        today_start = fields.Datetime.start_of(fields.Datetime.now(), 'day')
        prepared_return_notes_count = 0
        if self.env.user.has_group('werlen_repuestos_erp.group_reception'):
            prepared_return_notes_count = self.env['return_note'].search_count([
                ('state', '=', 'prepared'),
            ])
        return {
            'max_boxes': max_boxes,
            'columns': [
                {'key': 'pending_review', 'label': 'Pendientes',
                 'count': self.search_count([('state', '=', 'pending_review')])},
                {'key': 'in_review', 'label': 'En revisión',
                 'count': self.search_count([('state', '=', 'in_review')])},
                {'key': 'reviewed', 'label': 'Revisados hoy',
                 'count': self.search_count([
                     ('state', '=', 'reviewed'),
                     ('controlled_datetime_end', '>=', today_start),
                ])},
            ],
            'prepared_return_notes_count': prepared_return_notes_count,
            'can_create_reception': self.env.user.has_group(
                'werlen_repuestos_erp.group_reception'
            ),
        }

    def get_print_received_by(self):
        self.ensure_one()
        return ', '.join(self.who_received_ids.mapped('name'))

    def _validate_printable_content(self):
        self.ensure_one()
