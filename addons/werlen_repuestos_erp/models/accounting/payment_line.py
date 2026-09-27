from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

from ...enums.accounting.payment_origin_explanation import (
    PAYMENT_ORIGIN_EXPLANATION_ENUM,
    PAYMENT_ORIGIN_EXPLANATION_WITHOUT_RECONCILIATION_LIST,
)
from ...enums.accounting.payment_status import PAYMENT_STATUS_ENUM
from ...utils.group_verification import ensure_user_in_groups, ensure_write_allowed_fields


class PaymentLine(models.Model):
    _name = 'payment_line'
    _description = 'Registro de: Pago'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        default='Nuevo Pago',
        readonly=True,
        index=True,
    )

    payment_origin_explanation = fields.Selection(
        selection=PAYMENT_ORIGIN_EXPLANATION_ENUM,
        string='Razón del pago',
        default='non_operational',
        required=True,
        index=True,
    )

    payment_status = fields.Selection(
        selection=PAYMENT_STATUS_ENUM,
        string='Estado de reconciliación',
        default='not_paid',
        compute='_compute_amount_reconciliated',
        store=True,
        index=True,
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Moneda',
        store=True,
    )

    is_outgoing = fields.Boolean(string='Es saliente', required=True, default=False, index=True)
    amount = fields.Monetary(string='Importe', required=True)
    payment_method = fields.Many2one(
        comodel_name='payment_method',
        string='Método de pago',
        required=True,
    )
    confirmed = fields.Boolean(
        string='Confirmado',
        required=True,
        default=False,
        index=True,
        tracking=True,
    )
    journal = fields.Many2one(
        comodel_name='journal',
        string='Diario',
        required=True,
        tracking=True,
    )
    payee = fields.Many2one(
        comodel_name='res.partner',
        string='Recibe',
        required=True,
    )
    payer = fields.Many2one(
        comodel_name='res.partner',
        string='Paga',
        required=True,
    )

    confirmed_text = fields.Char(string='Estado de confirmación', compute='_compute_confirmed_text')

    amount_reconciliated = fields.Monetary(
        string='Importe reconciliado',
        compute='_compute_amount_reconciliated',
        store=True,
    )
    amount_not_reconciliated = fields.Monetary(
        string='Importe no reconciliado',
        compute='_compute_amount_reconciliated',
        store=True,
    )

    who_proposed_payment = fields.Many2one(comodel_name='res.users', string='Quién propuso el pago')
    who_confirmed_payment = fields.Many2one(comodel_name='res.users', string='Quién confirmó el pago')
    time_of_payment_proposal = fields.Datetime(string='Fecha de propuesta', index=True)
    time_of_payment_confirmation = fields.Datetime(string='Fecha de confirmación', index=True)
    observations = fields.Text(string='Observaciones', tracking=True)

    invoice_out_total_amount = fields.Monetary()
    invoice_out_amount_not_reconciliated = fields.Monetary()
    reconciliation_invoice_id = fields.Many2one(comodel_name='invoice_out')

    reconciliation_lines = fields.Many2many(
        comodel_name='reconciliation_line',
        compute='_compute_reconciliation_lines',
        string='Líneas de reconciliación',
    )
    reconciliation_lines_when_incomming = fields.One2many(
        comodel_name='reconciliation_line',
        inverse_name='payment_line_in_id',
        string='Reconciliaciones entrantes',
    )
    reconciliation_lines_when_outgoing = fields.One2many(
        comodel_name='reconciliation_line',
        inverse_name='payment_line_out_id',
        string='Reconciliaciones salientes',
    )

    def _get_reconciliation_lines(self):
        return (
            self.reconciliation_lines_when_outgoing
            if self.is_outgoing else self.reconciliation_lines_when_incomming
        )

    @api.depends('reconciliation_lines_when_incomming', 'reconciliation_lines_when_outgoing', 'is_outgoing')
    def _compute_reconciliation_lines(self):
        for record in self:
            record.reconciliation_lines = record._get_reconciliation_lines()

    @api.depends('confirmed')
    def _compute_confirmed_text(self):
        for record in self:
            record.confirmed_text = 'SI' if record.confirmed else 'NO'

    @api.depends(
        'amount',
        'reconciliation_lines_when_incomming',
        'reconciliation_lines_when_outgoing',
        'reconciliation_lines_when_incomming.amount',
        'reconciliation_lines_when_outgoing.amount',
        'payment_origin_explanation',
    )
    def _compute_amount_reconciliated(self):
        for record in self:
            lines = record._get_reconciliation_lines()
            record.amount_reconciliated = sum(lines.mapped('amount'))
            record.amount_not_reconciliated = record.amount - record.amount_reconciliated
            if record.payment_origin_explanation in PAYMENT_ORIGIN_EXPLANATION_WITHOUT_RECONCILIATION_LIST:
                record.payment_status = 'paid'
            elif record.amount_not_reconciliated <= record.amount * 0.01:
                record.payment_status = 'paid'
            elif record.amount_reconciliated > 0:
                record.payment_status = 'partially_paid'
            else:
                record.payment_status = 'not_paid'

    def get_is_outgoing(self):
        return self.is_outgoing

    def get_amount_not_reconciliated(self):
        return self.amount_not_reconciliated

    @api.model
    def _require_open_journal_session(self, journal_id):
        journal = self.env['journal'].browse(journal_id)
        if not journal.exists():
            raise UserError('El diario asociado no existe.')
        session = journal.sudo().current_cash_session
        if not session or session.state != 'open':
            raise UserError(
                f"No se puede confirmar el pago porque la caja '{journal.name}' no está abierta."
            )

    def _require_journal_allowed_users(self, journal_id):
        journal = self.env['journal'].browse(journal_id)
        if not journal.exists():
            raise ValidationError('El diario asociado no existe.')
        if not journal.allowed_users:
            raise ValidationError(f"El diario '{journal.name}' no tiene usuarios habilitados.")
        if self.env.user.id not in journal.allowed_users.ids and not self.env.su:
            raise ValidationError(
                f"No tienes permiso para confirmar movimientos en el diario '{journal.name}'."
            )

    def _require_payment_method_journal(self, payment_method_id, journal_id):
        payment_method = self.env['payment_method'].browse(payment_method_id)
        journal = self.env['journal'].browse(journal_id)
        if not payment_method.exists() or not journal.exists():
            raise ValidationError('El pago debe tener un método y un diario válidos.')
        if journal not in payment_method.allowed_journals:
            raise ValidationError(
                f"El diario '{journal.name}' no está permitido para el método "
                f"'{payment_method.name}'."
            )

    def confirm_payment(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja para confirmar pagos.',
        )
        if self.confirmed:
            raise UserError('El pago ya estaba confirmado.')
        self._require_payment_method_journal(self.payment_method.id, self.journal.id)
        self._require_journal_allowed_users(self.journal.id)
        self._require_open_journal_session(self.journal.id)
        self._confirm_payment_without_access_check()

    def _confirm_payment_without_access_check(self):
        self.ensure_one()
        self.sudo().write({
            'confirmed': True,
            'who_confirmed_payment': self.env.user.id,
            'time_of_payment_confirmation': fields.Datetime.now(),
        })
        self._get_reconciliation_lines().sudo().write({
            'confirmed': True,
        })
        session = self.journal.sudo().current_cash_session
        if session and session.state == 'open':
            session.sudo().write({'last_refresh_at': False})
            session.refresh_data()

        invoice_ids = self._get_reconciliation_lines().mapped('invoice_out_id')
        if invoice_ids:
            self.env['sale_fulfillment_order'].search([
                ('invoice_id', 'in', invoice_ids.ids),
            ])._update_payment_workflow()

    def _reverse_confirmation_of_payment(self):
        self.ensure_one()
        self._get_reconciliation_lines().sudo().write({
            'confirmed': False,
        })
        self.sudo().write({
            'confirmed': False,
            'who_confirmed_payment': False,
            'time_of_payment_confirmation': False,
        })
        session = self.journal.sudo().current_cash_session
        if session and session.state == 'open':
            session.sudo().write({'last_refresh_at': False})
            session.refresh_data()
        invoice_ids = self._get_reconciliation_lines().mapped('invoice_out_id')
        if invoice_ids:
            self.env['sale_fulfillment_order'].search([
                ('invoice_id', 'in', invoice_ids.ids),
            ])._update_payment_workflow()

    def try_reverse_confirmation(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja para revertir pagos.',
        )
        if not self.confirmed:
            raise UserError('El pago no está confirmado.')
        minutes = float(self.env['ir.config_parameter'].sudo().get_param(
            'werlen_repuestos_erp.max_minutes_passed_to_allow_undo_payment_last_step'
        ) or 1)
        elapsed = fields.Datetime.now() - self.time_of_payment_confirmation
        if elapsed.total_seconds() <= minutes * 60 or self.env.user.has_group(
            'werlen_repuestos_erp.group_administration'
        ):
            self._reverse_confirmation_of_payment()
        else:
            raise UserError('El pago fue confirmado hace demasiado tiempo para revertirlo.')

    def try_undo_last_step(self):
        self.ensure_one()
        if self.confirmed:
            self.try_reverse_confirmation()
        if not self.confirmed:
            self.unlink()

    def action_open_change_journal_wizard(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para cambiar el diario de un pago.',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Cambiar diario del pago',
            'res_model': 'wizard_change_payment_line_journal',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payment_line_id': self.id,
                'default_current_journal_id': self.journal.id,
            },
        }

    def _check_write_permissions_one(self, values):
        if not self.confirmed:
            return
        ensure_write_allowed_fields(
            self,
            self.env.user,
            values,
            {
                'werlen_repuestos_erp.group_accountant': {'observations'},
                'werlen_repuestos_erp.group_sales': {'observations'},
                'werlen_repuestos_erp.group_administration': {'observations'},
                'werlen_repuestos_erp.group_management': {'observations', 'journal'},
                'werlen_repuestos_erp.group_system': {'*'},
            },
        )

    def write(self, values):
        for record in self:
            record._check_write_permissions_one(values)
        return super().write(values)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('amount', 0) <= 0:
                raise UserError('El importe del pago debe ser mayor que 0.')
            if values.get('confirmed') and not self.env.su:
                ensure_user_in_groups(
                    self.env.user,
                    ['werlen_repuestos_erp.group_accountant'],
                    error_message='Necesitas permisos de Caja para confirmar pagos.',
                )
            values.setdefault('name', self.env['ir.sequence'].next_by_code('payment.line') or 'Nuevo Pago')
            values['who_proposed_payment'] = self.env.user.id
            values['time_of_payment_proposal'] = fields.Datetime.now()
            self._require_payment_method_journal(
                values.get('payment_method'),
                values.get('journal'),
            )
            if values.get('confirmed'):
                journal_id = values.get('journal')
                self._require_journal_allowed_users(journal_id)
                self._require_open_journal_session(journal_id)
                values['who_confirmed_payment'] = self.env.user.id
                values['time_of_payment_confirmation'] = fields.Datetime.now()
            else:
                values['who_confirmed_payment'] = False
                values['time_of_payment_confirmation'] = False
        records = super().create(vals_list)
        for record in records:
            if record.reconciliation_invoice_id:
                self.env['reconciliation_line'].create({
                    'outgoing_move_ref': f'invoice_out,{record.reconciliation_invoice_id.id}',
                    'incomming_move_ref': f'payment_line,{record.id}',
                    'amount': record.amount,
                    'confirmed': record.confirmed,
                })
        return records

    """ Dashboard methods """

    @api.model
    def get_available_journals(self):
        journals = self.env['journal'].search([])
        user = self.env.user
        return {
            'journals': [
                {'id': journal.id, 'name': journal.name}
                for journal in journals
            ],
            'default_journal_id': user.default_journal_id.id if user.default_journal_id else False,
        }

    @api.model
    def get_cashier_today_payments(self, journal_id=None):
        now = fields.Datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        domain = [
            ('confirmed', '=', True),
            ('time_of_payment_confirmation', '>=', today_start),
            ('time_of_payment_confirmation', '<=', today_end),
        ]
        try:
            journal_id = int(journal_id) if journal_id else False
        except (TypeError, ValueError):
            journal_id = False
        if journal_id:
            domain.append(('journal', '=', journal_id))

        payments = self.search(domain, order='time_of_payment_confirmation desc', limit=7)
        current_user = self.env.user
        origin_labels = dict(self._fields['payment_origin_explanation'].selection)
        result = []
        for payment in payments:
            user_time = fields.Datetime.context_timestamp(
                self, payment.time_of_payment_confirmation
            )
            result.append({
                'id': payment.id,
                'amount': payment.amount,
                'is_outgoing': payment.is_outgoing,
                'method': payment.payment_method.name if payment.payment_method else '',
                'origin': origin_labels.get(payment.payment_origin_explanation, ''),
                'description': (payment.observations or '')[:50],
                'confirmed_by': payment.who_confirmed_payment.name if payment.who_confirmed_payment else '',
                'confirmed_by_id': payment.who_confirmed_payment.id if payment.who_confirmed_payment else False,
                'proposed_by': payment.who_proposed_payment.name if payment.who_proposed_payment else '',
                'time': user_time.strftime('%H:%M') if user_time else '',
                'is_other_user': payment.who_confirmed_payment != current_user,
            })
        return result

    def unlink(self):
        for record in self:
            if record.confirmed:
                raise UserError('No se puede eliminar un pago confirmado.')
        return super().unlink()

    @api.constrains('amount', 'amount_reconciliated')
    def _check_amounts(self):
        for record in self:
            if float_compare(record.amount, record.amount_reconciliated, precision_digits=2) < 0:
                raise UserError('El importe reconciliado no puede superar el importe del pago.')
            if float_compare(record.amount, 0, precision_digits=2) <= 0:
                raise UserError('El importe del pago debe ser mayor que 0.')

    _sql_constraints = [
        (
            'payment_line_name_uniq',
            'UNIQUE(name)',
            'Ya existe una línea de pago con esta referencia.',
        ),
    ]
