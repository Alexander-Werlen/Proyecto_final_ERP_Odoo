from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from ...enums.purchases.return_note_state import RETURN_NOTE_STATE_ENUM
from ...utils.group_verification import ensure_user_in_groups


RETURN_NOTE_GROUPS = [
    'werlen_repuestos_erp.group_administration',
    'werlen_repuestos_erp.group_reception',
]


class ReturnNote(models.Model):
    _name = 'return_note'
    _description = 'Nota de devolución a proveedor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'name desc'

    name = fields.Char(string='Identificador', required=True, readonly=True,
                       index=True, copy=False, default='Nuevo')
    supplier_id = fields.Many2one('res.partner', string='Proveedor', required=True,
                                  tracking=True, domain=[('is_supplier', '=', True)])
    state = fields.Selection(RETURN_NOTE_STATE_ENUM, string='Estado', default='draft',
                             required=True, readonly=True, index=True, tracking=True)
    date = fields.Date(string='Fecha', default=fields.Date.today, tracking=True)
    package_count = fields.Char(string='Cantidad de bultos', default='1 Bulto', tracking=True)
    carrier_id = fields.Many2one('res.partner', string='Transportista',
                                 domain=[('is_carrier', '=', True)], tracking=True)
    observations = fields.Text(string='Observaciones', tracking=True)
    preparation_datetime = fields.Datetime(string='Fecha y hora de preparación', readonly=True)
    sent_datetime = fields.Datetime(string='Fecha y hora de envío', readonly=True)
    closing_datetime = fields.Datetime(string='Fecha y hora de cierre', readonly=True)
    line_ids = fields.One2many('return_line', 'return_note_id', string='Líneas de devolución')
    who_prepared_id = fields.Many2one('res.users', string='Preparada por', readonly=True)
    who_sent_id = fields.Many2one('res.users', string='Enviada por', readonly=True)
    who_closed_id = fields.Many2one('res.users', string='Cerrada por', readonly=True)
    who_created_id = fields.Many2one('res.users', string='Creada por',
                                     default=lambda self: self.env.user, readonly=True)
    creation_date = fields.Datetime(string='Fecha de creación', default=fields.Datetime.now,
                                    required=True, readonly=True, index=True)

    def get_print_lines(self):
        self.ensure_one()
        grouped = {}
        for line in self.line_ids:
            values = {
                'product_code': line.product_code or '',
                'product_description': line.product_description or '',
                'reason': line.reason or '',
                'observations': line.observations or '',
                'quantity': line.quantity,
            }
            key = tuple(values[field] for field in ('product_code', 'product_description', 'reason', 'observations'))
            if key in grouped:
                grouped[key]['quantity'] += line.quantity
            else:
                grouped[key] = values
        return list(grouped.values())

    def get_print_blank_row_count(self):
        return max(0, 6 - len(self.get_print_lines()))

    def get_print_supplier_data(self):
        self.ensure_one()
        supplier = self.supplier_id
        return {
            'name': supplier.name or '',
            'address': ', '.join(value for value in (supplier.street, supplier.street2) if value),
            'city': supplier.city or '',
            'zip': supplier.zip or '',
            'phone': supplier.phone or supplier.mobile or '',
        }

    def get_print_company_data(self):
        self.ensure_one()
        company = self.env.company
        partner = company.partner_id
        return {
            'name': company.name or partner.name or '',
            'address': ', '.join(value for value in (partner.street, partner.street2) if value),
            'location': ', '.join(value for value in (partner.city, partner.state_id.name if partner.state_id else '') if value),
            'phone': partner.phone or partner.mobile or company.phone or '',
            'email': partner.email or company.email or '',
            'website': partner.website or company.website or '',
            'tax_id': company.vat or partner.vat or '',
        }

    def _validate_printable_content(self):
        self.ensure_one()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('return.note')
        return super().create(vals_list)

    def _check_permission(self):
        ensure_user_in_groups(self.env.user, RETURN_NOTE_GROUPS,
                              error_message='No tiene permisos para gestionar notas de devolución.')

    def _log_action(self, action):
        self.ensure_one()
        timestamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        self.message_post(body=Markup(
            '<ul style="margin:0;padding-left:16px;">'
            f'<li><b>Acción:</b> {action}</li>'
            f'<li><b>Usuario:</b> {self.env.user.name}</li>'
            f'<li><b>Fecha:</b> {timestamp:%Y-%m-%d %H:%M:%S}</li>'
            '</ul>'
        ), message_type='comment', subtype_xmlid='mail.mt_note')

    def action_prepare(self):
        self.ensure_one(); self._check_permission()
        if self.state != 'draft':
            raise UserError('Solo se puede preparar una nota en borrador.')
        if not self.line_ids:
            raise UserError('No se puede preparar una nota sin líneas de devolución.')
        self.sudo().write({'state': 'prepared', 'preparation_datetime': fields.Datetime.now(),
                           'who_prepared_id': self.env.user.id})
        self._log_action('Preparó la nota de devolución.')

    def action_send(self):
        self.ensure_one(); self._check_permission()
        if self.state != 'prepared':
            raise UserError('Solo se puede enviar una nota preparada.')
        self.sudo().write({'state': 'sent', 'sent_datetime': fields.Datetime.now(),
                           'who_sent_id': self.env.user.id})
        self.line_ids.sudo().write({'state': 'sent'})
        self._log_action('Envió la nota de devolución.')

    def action_close(self):
        self.ensure_one(); self._check_permission()
        if self.state != 'sent':
            raise UserError('Solo se puede cerrar una nota enviada.')
        self.sudo().write({'state': 'closed', 'closing_datetime': fields.Datetime.now(),
                           'who_closed_id': self.env.user.id})
        self._log_action('Cerró la nota de devolución.')

    def action_reopen(self):
        self.ensure_one(); self._check_permission()
        if self.state != 'closed':
            raise UserError('Solo se puede reabrir una nota cerrada.')
        self.sudo().write({'state': 'draft', 'closing_datetime': False})
        self._log_action('Reabrió la nota de devolución.')

    def action_open_associate_claim(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asociar reclamo',
            'res_model': 'wizard_associate_return_line_claim',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_associate_return_line_claim_form_view'
            ).id,
            'target': 'new',
            'context': {'default_return_note_id': self.id},
        }
