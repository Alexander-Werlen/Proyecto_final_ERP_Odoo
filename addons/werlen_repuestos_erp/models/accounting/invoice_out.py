from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ...utils.group_verification import ensure_write_allowed_fields, ensure_user_in_groups
from ...enums.accounting.payment_status import PAYMENT_STATUS_ENUM

class InvoiceOut(models.Model):
    _name = 'invoice_out'
    _rec_name = 'invoice_id'
    _description = "Registro de: Factura Emitida"

    """ Basic identifiers """
    invoice_id = fields.Char(
        string='Número',
        required=True,
        index=True
    )

    sales_point = fields.Char(
        string='Punto de Venta',
        compute='_compute_sales_point',
        store=True,
        index=True,
        readonly=True,
        help="Segmento de 4 dígitos extraído del identificador (XX-X-<punto_de_venta>-XXXXXXXX).",
    )

    invoice_type = fields.Many2one(
        'invoice_type',
        string='Tipo',
        required=True
    )

    """ Currency needed to allow monetary fields """
    company_id = fields.Many2one(
        'res.company', store=True, copy=False,
        string="Company",
        default=lambda self: self.env.user.company_id.id
    )

    currency_id = fields.Many2one(
        'res.currency', string="Currency",
        related='company_id.currency_id',
    )

    """ Invoice Info """
    client = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True
    )

    client_identifier = fields.Char(
        string='Num Cliente',
        related='client.unique_identifier',
        store=True,
        readonly=True
    )

    full_name = fields.Char(
        string='Nombre completo',
    )

    total_cost = fields.Monetary(
        string='Importe',
        required=True,
    )

    billing_base_amount = fields.Monetary(
        string='Importe base',
        compute='_compute_billing_base_amount',
        store=True,
    )

    city = fields.Many2one(
        'city',
        string='Ciudad',
    )

    state = fields.Many2one(
        'res.country.state',
        string='Provincia',
    )

    zip_code = fields.Char(
        string='Zip',
    )

    destination = fields.Char(
        string='Destino',
    )

    cellphone = fields.Char(
        string='Telefono',
    )

    seller = fields.Many2one(
        'res.users',
        string='Vendedor',
        required=True,
        default=lambda self: self.env.user
    )

    date = fields.Datetime(
        string='Fecha',
        index=True,
        default=fields.Datetime.now
    )

    observations = fields.Text(
        string='Observaciones'
    )

    payment_method = fields.Many2one(
        'payment_method',
        help="Es el medio de pago utilizado en la factura emitida. Puede ser diferente al real.",
        string='Cond. Venta',
        required=True
    )

    is_account_move = fields.Boolean(
        string='Cuenta Corriente',
        related='payment_method.is_account_payment_method',
        store=True,
        readonly=True,
    )

    payment_status = fields.Selection(
        selection=PAYMENT_STATUS_ENUM,
        string='Estado de pago',
        compute='_compute_payment_amounts',
        store=True,
        default='not_paid',
        required=True,
        index=True,
    )

    amount_paid_confirmed = fields.Monetary(
        string='Importe pagado confirmado',
        compute='_compute_payment_amounts',
        store=True,
    )

    amount_paid_unconfirmed = fields.Monetary(
        string='Importe pagado',
        compute='_compute_payment_amounts',
        store=True,
    )

    amount_not_paid_confirmed = fields.Monetary(
        string='Importe no pagado confirmado',
        compute='_compute_payment_amounts',
        store=True,
    )

    amount_not_paid_unconfirmed = fields.Monetary(
        string='Importe no pagado',
        compute='_compute_payment_amounts',
        store=True,
    )

    point_of_sale = fields.Many2one(
        comodel_name='point_of_sale',
        string='Punto de venta',
    )

    is_draft = fields.Boolean(
        string='Es Borrador',
        default=True
    )

    is_manual_invoice = fields.Boolean(
        string='Creado manualmente',
        default=True
    )

    related_credit_notes = fields.One2many(
        comodel_name='credit_note_out',
        inverse_name='related_invoice',
        string='Notas de crédito relacionadas',
    )

    reconciliation_lines = fields.One2many(
        comodel_name='reconciliation_line',
        inverse_name='invoice_out_id',
        string='Reconciliaciones',
    )

    """ Computed methods """

    @api.depends('invoice_id')
    def _compute_sales_point(self):
        for record in self:
            record.sales_point = self._extract_sales_point(record.invoice_id)

    @api.depends('total_cost', 'payment_method', 'payment_method.billing_coefficient')
    def _compute_billing_base_amount(self):
        for record in self:
            coefficient = record.payment_method.billing_coefficient if record.payment_method else 1.0
            record.billing_base_amount = record.total_cost * coefficient

    @api.depends(
        'reconciliation_lines',
        'reconciliation_lines.amount',
        'reconciliation_lines.confirmed',
        'is_account_move',
    )
    def _compute_payment_amounts(self):
        for record in self:
            if record.is_account_move:
                record.amount_paid_confirmed = record.total_cost
                record.amount_paid_unconfirmed = record.total_cost
                record.amount_not_paid_confirmed = 0.0
                record.amount_not_paid_unconfirmed = 0.0
                record.payment_status = 'account'
                continue

            confirmed = sum(line.amount for line in record.reconciliation_lines if line.confirmed)
            total = sum(record.reconciliation_lines.mapped('amount'))
            record.amount_paid_confirmed = confirmed
            record.amount_paid_unconfirmed = total
            record.amount_not_paid_confirmed = record.total_cost - confirmed
            record.amount_not_paid_unconfirmed = record.total_cost - total

            tolerance = record.total_cost * 0.01
            if record.amount_not_paid_confirmed <= tolerance:
                record.payment_status = 'paid'
            elif confirmed > 0:
                record.payment_status = 'partially_paid'
            else:
                record.payment_status = 'not_paid'

    @staticmethod
    def _extract_sales_point(identifier):
        if not identifier or not isinstance(identifier, str):
            return False
        parts = identifier.split('-')
        if len(parts) >= 4 and len(parts[2]) == 4 and parts[2].isdigit():
            return parts[2]
        return False

    def get_is_outgoing(self):
        return True

    def get_amount_not_reconciliated(self):
        return self.amount_not_paid_unconfirmed

    def show_reconciliation_lines(self):
        self.ensure_one()
        return {
            'name': f'Reconciliaciones de {self.invoice_id}',
            'view_mode': 'list',
            'res_model': 'reconciliation_line',
            'type': 'ir.actions.act_window',
            'domain': [('invoice_out_id', '=', self.id)],
            'view_id': self.env.ref(
                'werlen_repuestos_erp.reconciliation_line_list_view'
            ).id,
        }

    def show_payment_lines(self):
        self.ensure_one()
        return {
            'name': f'Pagos asociados a {self.invoice_id}',
            'view_mode': 'list,form',
            'res_model': 'payment_line',
            'type': 'ir.actions.act_window',
            'domain': [('reconciliation_lines_when_incomming', 'in', self.reconciliation_lines.ids)],
            'views': [
                (self.env.ref('werlen_repuestos_erp.default_payment_line_list_view').id, 'list'),
                (self.env.ref('werlen_repuestos_erp.default_payment_line_form_view').id, 'form'),
            ],
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
                'default_outgoing_move_ref': f'invoice_out,{self.id}',
                'default_amount': max(self.amount_not_paid_unconfirmed, 0.0),
            },
            'view_id': self.env.ref('werlen_repuestos_erp.manual_reconciliation_line_form_view').id,
        }

    """ Actions """

    def confirm_draft(self):
        # ACCESS CHECK
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_sales'],
            error_message="Necesitas permisos de Ventas, no puedes crear facturas manuales.",
        )

        self.ensure_one()
        if self.is_draft is False:
            raise UserError("La factura ya estaba confirmada")

        # ACTION START
        self.is_manual_invoice = True
        self.is_draft = False

        fulfillment_order_vals = {
            'sale_fulfillment_order_id': self.invoice_id,
            'invoice_id': self.id,
            'point_of_sale': self.point_of_sale.id,
            'city': self.city.id,
            'zip_code': self.zip_code,
            'state': self.state.id,
            'destination': self.destination,
            'logistical_status': 'draft'
        }

        self.env['sale_fulfillment_order'].create(fulfillment_order_vals)

    """ Overrides """

    def _check_write_permissions_one(self, vals):

        if self.is_draft:
            return

        user = self.env.user

        EDITABLE_FIELDS_BY_GROUP = {
            'werlen_repuestos_erp.group_administration': {
                'observations',
            },
            'werlen_repuestos_erp.group_system': {
                '*'
            },
        }

        ensure_write_allowed_fields(self, user, vals, EDITABLE_FIELDS_BY_GROUP)

    def _check_write_permissions(self, vals):
        for rec in self:
            rec._check_write_permissions_one(vals)

    def write(self, vals):
        self._check_write_permissions(vals)
        return super().write(vals)

    """ SQL Constraints """

    _sql_constraints = [
        # Identificador único del modelo
        (
            'invoice_unique',
            'UNIQUE(invoice_id, invoice_type, company_id)',
            'Ya existe una factura con ese número, tipo y compañía.'
        ),

        # Campos required=True (validación a nivel BD)
        (
            'invoice_id_not_null',
            'CHECK(invoice_id IS NOT NULL AND invoice_id <> \'\')',
            'El número de factura es obligatorio.'
        ),
        (
            'invoice_type_not_null',
            'CHECK(invoice_type IS NOT NULL)',
            'El tipo de factura es obligatorio.'
        ),
        (
            'client_not_null',
            'CHECK(client IS NOT NULL)',
            'El cliente es obligatorio.'
        ),
        (
            'seller_not_null',
            'CHECK(seller IS NOT NULL)',
            'El vendedor es obligatorio.'
        ),
        (
            'total_cost_not_null',
            'CHECK(total_cost IS NOT NULL)',
            'El importe total es obligatorio.'
        ),
        (
            'payment_method_not_null',
            'CHECK(payment_method IS NOT NULL)',
            'El método de pago es obligatorio.'
        ),
        (
            'payment_status_not_null',
            'CHECK(payment_status IS NOT NULL)',
            'El estado de pago es obligatorio.',
        ),

    ]
