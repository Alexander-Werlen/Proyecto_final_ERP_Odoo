from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ...enums.accounting.payment_status import PAYMENT_STATUS_ENUM
from ...utils.group_verification import ensure_user_in_groups


class AccountPayment(models.Model):
    _name = 'account_payment'
    _description = 'Registro de: Recibo de cuenta corriente'
    _rec_name = 'account_payment_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    account_payment_id = fields.Char(
        string='Identificador',
        required=True,
        readonly=True,
        index=True,
    )

    sales_point = fields.Char(
        string='Punto de venta',
        compute='_compute_sales_point',
        store=True,
        index=True,
        readonly=True,
    )

    client = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
        required=True,
        readonly=True,
    )

    amount = fields.Monetary(string='Importe', required=True, readonly=True)

    discount_amount = fields.Monetary(
        string='Descuento',
        required=True,
        default=0.0,
        readonly=True,
    )

    date = fields.Datetime(
        string='Fecha',
        required=True,
        readonly=True,
        index=True,
    )

    is_main_point_of_sale_category = fields.Boolean(
        string='Es punto de venta principal',
        default=True,
        readonly=True,
    )

    payment_status = fields.Selection(
        selection=PAYMENT_STATUS_ENUM,
        string='Estado de pago',
        default='not_paid',
        compute='_compute_amount_reconciliated',
        store=True,
        required=True,
        readonly=True,
        index=True,
    )

    status = fields.Selection(
        selection=[('draft', 'Borrador'), ('verified', 'Verificado')],
        string='Estado',
        default='draft',
        required=True,
        readonly=True,
        index=True,
        tracking=True,
    )

    who_created = fields.Many2one(
        comodel_name='res.users',
        string='Creador',
        default=lambda self: self.env.user,
        readonly=True,
    )

    amount_reconciliated_confirmed = fields.Monetary(
        string='Importe reconciliado confirmado',
        compute='_compute_amount_reconciliated',
        store=True,
    )

    amount_not_reconciliated_confirmed = fields.Monetary(
        string='Importe no reconciliado confirmado',
        compute='_compute_amount_reconciliated',
        store=True,
    )

    amount_reconciliated_unconfirmed = fields.Monetary(
        string='Importe reconciliado',
        compute='_compute_amount_reconciliated',
        store=True,
    )

    amount_not_reconciliated_unconfirmed = fields.Monetary(
        string='Importe no reconciliado',
        compute='_compute_amount_reconciliated',
        store=True,
    )

    observations = fields.Text(string='Observaciones', tracking=True)

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

    reconciliation_lines = fields.One2many(
        comodel_name='reconciliation_line',
        inverse_name='account_payment_id',
        string='Reconciliaciones',
    )

    @api.depends('account_payment_id')
    def _compute_sales_point(self):
        for record in self:
            parts = (record.account_payment_id or '').split('-')
            record.sales_point = (
                parts[2] if len(parts) >= 4 and len(parts[2]) == 4 and parts[2].isdigit() else False
            )

    @api.depends(
        'reconciliation_lines',
        'reconciliation_lines.amount',
        'reconciliation_lines.confirmed',
    )
    def _compute_amount_reconciliated(self):
        for record in self:
            confirmed = sum(
                line.amount for line in record.reconciliation_lines if line.confirmed
            )
            total = sum(record.reconciliation_lines.mapped('amount'))
            record.amount_reconciliated_confirmed = confirmed
            record.amount_reconciliated_unconfirmed = total
            record.amount_not_reconciliated_confirmed = record.amount - confirmed
            record.amount_not_reconciliated_unconfirmed = record.amount - total

            if record.amount_not_reconciliated_confirmed <= record.amount * 0.01:
                record.payment_status = 'paid'
            elif confirmed > 0:
                record.payment_status = 'partially_paid'
            else:
                record.payment_status = 'not_paid'

    def get_is_outgoing(self):
        return True

    def get_amount_not_reconciliated(self):
        return self.amount_not_reconciliated_unconfirmed

    def create_new_payment(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja para crear pagos a cuenta corriente.',
        )
        return {
            'name': 'Ingreso a cuenta corriente',
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_current_account_income',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payer_id': self.client.id,
                'default_amount': max(self.amount_not_reconciliated_unconfirmed, 0.0),
                'default_account_payment_for_auto_reconciliation': self.id,
                'default_journal_id': self.env.user.default_journal_id.id,
            },
        }

    def open_manual_reconciliation_line_form(self):
        self.ensure_one()
        return {
            'name': 'Reconciliación manual',
            'type': 'ir.actions.act_window',
            'res_model': 'transient_reconciliation_line',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_outgoing_move_ref': f'account_payment,{self.id}',
                'default_amount': max(self.amount_not_reconciliated_unconfirmed, 0.0),
                'from_account_payment_manual_reconciliation': True,
            },
            'view_id': self.env.ref('werlen_repuestos_erp.manual_reconciliation_line_form_view').id,
        }

    def action_start_verification(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja para verificar recibos.',
        )
        wizard = self.env['wizard_verification_account_payment'].create({
            'account_payment': self.id,
            'client': self.client.id,
            'amount': self.amount,
            'discount_amount': self.discount_amount,
            'date': self.date,
            'who_created': self.who_created.id if self.who_created else self.env.user.id,
            'observations': self.observations,
            'previous_amount_reconciliated': self.amount_reconciliated_unconfirmed,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_verification_account_payment',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def show_reconciliation_lines(self):
        self.ensure_one()
        return {
            'name': f'Reconciliaciones de {self.account_payment_id}',
            'type': 'ir.actions.act_window',
            'res_model': 'reconciliation_line',
            'view_mode': 'list',
            'domain': [('account_payment_id', '=', self.id)],
        }

    @api.constrains('amount', 'amount_reconciliated_unconfirmed')
    def _check_amount_reconciliated(self):
        for record in self:
            if float_compare(record.amount, 0, precision_digits=2) <= 0:
                raise UserError('El importe del recibo debe ser mayor que 0.')

    _sql_constraints = [
        (
            'account_payment_id_uniq',
            'UNIQUE(account_payment_id, company_id)',
            'Ya existe un recibo con ese identificador.',
        ),
    ]
