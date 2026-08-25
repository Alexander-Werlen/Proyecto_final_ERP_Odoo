from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

from ...enums.accounting.payment_origin_explanation import (
    PAYMENT_ORIGIN_EXPLANATION_ENUM,
    PAYMENT_ORIGIN_EXPLANATION_WITHOUT_RECONCILIATION_LIST,
)
from ...enums.accounting.payment_status import PAYMENT_STATUS_ENUM
from ...utils.group_verification import ensure_user_in_groups


class Check(models.Model):
    _name = 'check'
    _description = 'Registro de: Cheque'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    payment_origin_explanation = fields.Selection(
        selection=PAYMENT_ORIGIN_EXPLANATION_ENUM,
        string='Razón del cheque',
        default='account_in',
        required=True,
        index=True,
        tracking=True,
    )

    check_number = fields.Char(string='Número', required=True, index=True, tracking=True)

    bank = fields.Many2one(
        comodel_name='res.bank',
        string='Banco',
        required=True,
        tracking=True,
    )

    issuer = fields.Char(
        string='CUIT y nombre del emisor',
        required=True,
        index=True,
        tracking=True,
    )

    owner_of_credit = fields.Many2one(
        comodel_name='res.partner',
        string='Propietario del crédito',
        required=True,
        tracking=True,
    )

    amount = fields.Monetary(string='Monto', required=True, tracking=True)

    collection_date = fields.Date(string='Fecha de cobro', required=True, tracking=True)

    city = fields.Many2one(
        comodel_name='city',
        string='Ciudad',
        required=True,
        tracking=True,
    )

    journal_id = fields.Many2one(
        comodel_name='journal',
        string='Diario/Caja actual',
        required=True,
        tracking=True,
        ondelete='restrict',
    )

    previous_journal_id = fields.Many2one(
        comodel_name='journal',
        string='Diario anterior',
        readonly=True,
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

    time_of_creation = fields.Datetime(
        string='Fecha de creación',
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    observations = fields.Text(string='Observaciones', tracking=True)

    who_created = fields.Many2one(
        comodel_name='res.users',
        string='Registrado por',
        default=lambda self: self.env.user,
    )

    amount_reconciliated = fields.Monetary(
        string='Importe reconciliado',
        compute='_compute_amount_reconciliated',
        store=True,
        tracking=True,
    )

    amount_not_reconciliated = fields.Monetary(
        string='Importe no reconciliado',
        compute='_compute_amount_reconciliated',
        store=True,
    )

    payment_status = fields.Selection(
        selection=PAYMENT_STATUS_ENUM,
        string='Estado de reconciliación',
        default='not_paid',
        compute='_compute_amount_reconciliated',
        store=True,
        index=True,
    )

    reconciliation_lines = fields.One2many(
        comodel_name='reconciliation_line',
        inverse_name='check_id',
        string='Reconciliaciones',
    )

    display_name = fields.Char(
        string='Identificador',
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('bank', 'check_number', 'issuer')
    def _compute_display_name(self):
        for record in self:
            bank_name = record.bank.name if record.bank else 'X'
            record.display_name = (
                f'CH-{bank_name}-{record.check_number or "X"}-{record.issuer or "X"}'
            )

    def name_get(self):
        return [(record.id, record.display_name) for record in self]

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        domain = args
        if name:
            domain = [
                '|', '|',
                ('check_number', operator, name),
                ('issuer', operator, name),
                ('bank.name', operator, name),
            ] + args
        return self.search(domain, limit=limit).name_get()

    @api.depends(
        'reconciliation_lines',
        'reconciliation_lines.amount',
        'amount',
        'payment_origin_explanation',
    )
    def _compute_amount_reconciliated(self):
        for record in self:
            record.amount_reconciliated = sum(record.reconciliation_lines.mapped('amount'))
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
        return False

    def get_amount_not_reconciliated(self):
        return self.amount_not_reconciliated

    def action_open_change_journal_wizard(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para cambiar el diario de un cheque.',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Cambiar diario del cheque',
            'res_model': 'wizard_change_check_journal',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_check_id': self.id,
                'default_current_journal_id': self.journal_id.id,
            },
        }

    @api.model
    def _require_journal_allowed_users(self, journal_id):
        journal = self.env['journal'].browse(journal_id)
        if not journal.exists():
            raise ValidationError('El diario asociado no existe.')
        if not journal.allowed_users:
            raise ValidationError(
                f"El diario '{journal.name}' no tiene usuarios habilitados."
            )
        if self.env.user.id not in journal.allowed_users.ids and not self.env.su:
            raise ValidationError(
                f"No tienes permiso para registrar cheques en el diario '{journal.name}'."
            )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('amount', 0) <= 0:
                raise UserError('El monto del cheque debe ser mayor que 0.')
            self._require_journal_allowed_users(values.get('journal_id'))
        return super().create(vals_list)

    @api.constrains('amount', 'amount_reconciliated')
    def _check_amounts(self):
        for record in self:
            if float_compare(record.amount, record.amount_reconciliated, precision_digits=2) < 0:
                raise UserError(
                    'El importe total reconciliado no puede ser mayor al importe del cheque.'
                )

    _sql_constraints = [
        (
            'check_unique',
            'UNIQUE(check_number, bank, issuer, company_id)',
            'Ya existe un cheque con ese número, banco, emisor y compañía.',
        ),
    ]
