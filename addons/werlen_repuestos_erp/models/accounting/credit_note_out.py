from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ...enums.accounting.payment_status import PAYMENT_STATUS_ENUM
from ...utils.group_verification import ensure_user_in_groups, ensure_write_allowed_fields


class CreditNoteOut(models.Model):
    _name = 'credit_note_out'
    _description = 'Registro de: Nota de crédito emitida'
    _rec_name = 'credit_note_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    credit_note_id = fields.Char(string='Número', required=True, index=True)

    sales_point = fields.Char(
        string='Punto de venta',
        compute='_compute_sales_point',
        store=True,
        index=True,
        readonly=True,
    )

    invoice_type = fields.Many2one(
        comodel_name='invoice_type',
        string='Tipo',
        required=True,
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

    state = fields.Selection(
        selection=[('draft', 'Borrador'), ('verified', 'Verificada')],
        string='Estado',
        default='draft',
        required=True,
        index=True,
        tracking=True,
    )

    client = fields.Many2one(
        comodel_name='res.partner',
        string='Propietario del crédito',
        required=True,
    )

    client_identifier = fields.Char(
        related='client.unique_identifier',
        string='Número de cliente',
        store=True,
        readonly=True,
    )

    full_name = fields.Char(string='Nombre del propietario', index=True)

    total_amount = fields.Monetary(
        string='Importe',
        required=True,
        readonly=True,
    )

    billing_base_amount = fields.Monetary(
        string='Importe base',
        compute='_compute_billing_base_amount',
        store=True,
    )

    related_invoice = fields.Many2one(
        comodel_name='invoice_out',
        string='Factura origen',
        tracking=True,
    )

    seller_of_related_invoice = fields.Many2one(
        comodel_name='res.users',
        string='Vendedor de la factura origen',
    )

    date = fields.Datetime(string='Fecha de emisión', required=True, index=True)

    payment_status = fields.Selection(
        selection=PAYMENT_STATUS_ENUM,
        string='Estado de pago',
        default='not_paid',
        compute='_compute_amount_reconciliated',
        store=True,
        required=True,
        readonly=True,
        index=True,
        tracking=True,
    )

    payment_method = fields.Many2one(
        comodel_name='payment_method',
        string='Condición de venta',
        required=True,
    )

    is_account_move = fields.Boolean(
        string='Cuenta Corriente',
        related='payment_method.is_account_payment_method',
        store=True,
        readonly=True,
    )

    is_manual_invoice = fields.Boolean(string='Creado manualmente', default=True)
    observations = fields.Text(string='Observaciones', tracking=True)

    who_approved = fields.Many2one(
        comodel_name='res.users',
        string='Aprobado por',
        tracking=True,
    )

    who_created = fields.Many2one(
        comodel_name='res.users',
        string='Emitida por',
        tracking=True,
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

    reconciliation_lines = fields.One2many(
        comodel_name='reconciliation_line',
        inverse_name='credit_note_out_id',
        string='Reconciliaciones',
    )

    @api.depends('credit_note_id')
    def _compute_sales_point(self):
        for record in self:
            parts = (record.credit_note_id or '').split('-')
            record.sales_point = (
                parts[2] if len(parts) >= 4 and len(parts[2]) == 4 and parts[2].isdigit() else False
            )

    @api.depends('total_amount', 'payment_method', 'payment_method.billing_coefficient')
    def _compute_billing_base_amount(self):
        for record in self:
            coefficient = record.payment_method.billing_coefficient if record.payment_method else 1.0
            record.billing_base_amount = record.total_amount * coefficient

    @api.depends(
        'total_amount',
        'reconciliation_lines',
        'reconciliation_lines.amount',
        'reconciliation_lines.confirmed',
        'is_account_move',
    )
    def _compute_amount_reconciliated(self):
        for record in self:
            total = sum(record.reconciliation_lines.mapped('amount'))
            confirmed = sum(
                line.amount for line in record.reconciliation_lines if line.confirmed
            )
            record.amount_reconciliated_confirmed = confirmed
            record.amount_reconciliated_unconfirmed = total
            record.amount_not_reconciliated_confirmed = record.total_amount - confirmed
            record.amount_not_reconciliated_unconfirmed = record.total_amount - total

            if record.is_account_move:
                record.payment_status = 'account'
            elif record.amount_reconciliated_confirmed > record.total_amount:
                record.payment_status = 'partially_paid'
            elif record.amount_not_reconciliated_confirmed <= record.total_amount * 0.01:
                record.payment_status = 'paid'
            elif confirmed > 0:
                record.payment_status = 'partially_paid'
            else:
                record.payment_status = 'not_paid'

    def get_is_outgoing(self):
        return False

    def get_amount_not_reconciliated(self):
        return self.amount_not_reconciliated_unconfirmed

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            ensure_user_in_groups(
                self.env.user,
                [
                    'werlen_repuestos_erp.group_sales',
                    'werlen_repuestos_erp.group_administration',
                    'werlen_repuestos_erp.group_system',
                ],
                error_message='Necesitas permisos para crear notas de crédito.',
            )
        for values in vals_list:
            if values.get('total_amount', 0) <= 0:
                raise UserError('El importe de la nota de crédito debe ser mayor que 0.')
            if values.get('state') == 'verified' and not self.env.su:
                raise UserError('Las notas de crédito nuevas deben comenzar en borrador.')
            if not self.env.su:
                values['state'] = 'draft'
                values.setdefault('who_created', self.env.user.id)
        return super().create(vals_list)

    def action_start_verification(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_administration'],
            error_message='Necesitas permisos de Administración para verificar notas de crédito.',
        )
        wizard = self.env['wizard_verification_credit_note_out'].create({
            'credit_note': self.id,
            'credit_note_id': self.credit_note_id,
            'client': self.client.id,
            'full_name': self.full_name,
            'total_amount': self.total_amount,
            'date': self.date,
            'seller_of_related_invoice': self.seller_of_related_invoice.id,
            'who_created': self.who_created.id or self.env.user.id,
            'who_approved': self.env.user.id,
            'related_invoice': self.related_invoice.id,
            'observations': self.observations,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Verificar nota de crédito',
            'res_model': 'wizard_verification_credit_note_out',
            'res_id': wizard.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_verification_credit_note_out_form_view'
            ).id,
            'target': 'new',
        }

    def create_payment(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja para reembolsar notas de crédito.',
        )
        if self.state != 'verified':
            raise UserError('Sólo se pueden reembolsar notas de crédito verificadas.')
        payment_method = self.env.ref(
            'werlen_repuestos_erp.payment_method_efectivo',
            raise_if_not_found=False,
        )
        wizard = self.env['wizard_payment_line_out_credit_note'].create({
            'credit_note_out_id': self.id,
            'amount': max(self.amount_not_reconciliated_unconfirmed, 0.0),
            'payee': self.client.id,
            'payment_method': payment_method.id if payment_method else False,
            'journal': payment_method.get_default_journal(self.env.user).id if payment_method else self.env.user.default_journal_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_payment_line_out_credit_note',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def show_reconciliation_lines(self):
        self.ensure_one()
        return {
            'name': f'Reconciliaciones de {self.credit_note_id}',
            'type': 'ir.actions.act_window',
            'res_model': 'reconciliation_line',
            'view_mode': 'list',
            'domain': [('credit_note_out_id', '=', self.id)],
        }

    def show_payment_lines(self):
        self.ensure_one()
        return {
            'name': f'Pagos asociados a {self.credit_note_id}',
            'type': 'ir.actions.act_window',
            'res_model': 'payment_line',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('werlen_repuestos_erp.default_payment_line_list_view').id, 'list'),
                (self.env.ref('werlen_repuestos_erp.default_payment_line_form_view').id, 'form'),
            ],
            'domain': [('reconciliation_lines_when_outgoing', 'in', self.reconciliation_lines.ids)],
        }

    def write(self, values):
        if self.env.su:
            return super().write(values)
        for record in self:
            ensure_write_allowed_fields(
                record,
                self.env.user,
                values,
                {
                    'werlen_repuestos_erp.group_sales': {'observations'},
                    'werlen_repuestos_erp.group_accountant': {'observations'},
                    'werlen_repuestos_erp.group_administration': {'observations'},
                    'werlen_repuestos_erp.group_management': {'observations'},
                    'werlen_repuestos_erp.group_system': {'*'},
                },
            )
        return super().write(values)

    @api.constrains('total_amount', 'amount_reconciliated_unconfirmed')
    def _check_amounts(self):
        for record in self:
            if float_compare(
                record.total_amount,
                record.amount_reconciliated_unconfirmed,
                precision_digits=2,
            ) < 0:
                raise UserError(
                    'El importe total reconciliado no puede ser mayor al importe de la nota de crédito.'
                )

    _sql_constraints = [
        (
            'credit_note_unique',
            'UNIQUE(credit_note_id, invoice_type, company_id)',
            'Ya existe una nota de crédito con ese número, tipo y compañía.',
        ),
    ]
