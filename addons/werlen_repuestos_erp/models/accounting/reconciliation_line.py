from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ...enums.accounting.reconciliation_fields import (
    INCOMMING_FIELDS,
    INCOMMING_MODELS,
    MODEL_IN_TO_FIELD,
    MODEL_OUT_TO_FIELD,
    OUTGOING_FIELDS,
    OUTGOING_MODELS,
)
from ...utils.group_verification import ensure_write_allowed_fields


class ReconciliationLine(models.Model):
    _name = 'reconciliation_line'
    _description = 'Registro de: Línea de reconciliación'

    amount = fields.Monetary(string='Importe', required=True, readonly=True)

    confirmed = fields.Boolean(string='Confirmada', default=False, readonly=True)

    outgoing_move_ref = fields.Reference(
        selection=OUTGOING_MODELS,
        string='Movimiento saliente',
        required=True,
    )

    incomming_move_ref = fields.Reference(
        selection=INCOMMING_MODELS,
        string='Movimiento entrante',
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

    payment_line_in_id = fields.Many2one(
        comodel_name='payment_line',
        string='Pago entrante',
        compute='_compute_relational_models_by_references',
        store=True,
        readonly=True,
        ondelete='cascade',
    )

    check_id = fields.Many2one(
        comodel_name='check',
        string='Cheque',
        compute='_compute_relational_models_by_references',
        store=True,
        readonly=True,
        ondelete='cascade',
    )

    payment_line_out_id = fields.Many2one(
        comodel_name='payment_line',
        string='Pago saliente',
        compute='_compute_relational_models_by_references',
        store=True,
        readonly=True,
        ondelete='cascade',
    )

    invoice_out_id = fields.Many2one(
        comodel_name='invoice_out',
        string='Factura emitida',
        compute='_compute_relational_models_by_references',
        store=True,
        readonly=True,
        ondelete='cascade',
    )

    credit_note_out_id = fields.Many2one(
        comodel_name='credit_note_out',
        string='Nota de crédito',
        compute='_compute_relational_models_by_references',
        store=True,
        readonly=True,
        ondelete='cascade',
    )

    account_payment_id = fields.Many2one(
        comodel_name='account_payment',
        string='Recibo CC',
        compute='_compute_relational_models_by_references',
        store=True,
        readonly=True,
        ondelete='cascade',
    )

    auxiliar_is_confirmed = fields.Char(
        string='Estado',
        compute='_compute_auxiliar_is_confirmed',
        store=True,
    )

    @staticmethod
    def _reference_model_names():
        return {
            'incoming': {model for model, _label in INCOMMING_MODELS},
            'outgoing': {model for model, _label in OUTGOING_MODELS},
        }

    @staticmethod
    def _available_amount(record):
        try:
            return record.get_amount_not_reconciliated()
        except AttributeError as error:
            raise UserError('El movimiento seleccionado no puede participar de una reconciliación.') from error

    @classmethod
    def _validate_reconciliation_values(cls, env, values):
        outgoing_ref = values.get('outgoing_move_ref')
        incoming_ref = values.get('incomming_move_ref')
        if not outgoing_ref or not incoming_ref:
            raise UserError('La reconciliación debe indicar ambos movimientos.')

        outgoing_model, outgoing_id = outgoing_ref.split(',', 1)
        incoming_model, incoming_id = incoming_ref.split(',', 1)
        names = cls._reference_model_names()
        if outgoing_model not in names['outgoing']:
            raise UserError('El movimiento saliente de la reconciliación es inválido.')
        if incoming_model not in names['incoming']:
            raise UserError('El movimiento entrante de la reconciliación es inválido.')

        outgoing = env[outgoing_model].browse(int(outgoing_id)).exists()
        incoming = env[incoming_model].browse(int(incoming_id)).exists()
        if not outgoing or not incoming:
            raise UserError('Uno de los movimientos seleccionados no existe.')
        if not outgoing.get_is_outgoing() or incoming.get_is_outgoing():
            raise UserError('La dirección de los movimientos de la reconciliación es inválida.')

        if outgoing_model == 'account_payment' and incoming_model not in {'payment_line', 'check'}:
            raise UserError('Los recibos sólo se pueden reconciliar con pagos y cheques.')
        if outgoing_model == 'invoice_out' and getattr(outgoing, 'is_account_move', False):
            raise UserError('Las facturas de cuenta corriente no se pueden reconciliar.')
        if incoming_model == 'credit_note_out' and getattr(incoming, 'is_account_move', False):
            raise UserError('Las notas de crédito de cuenta corriente no se pueden reconciliar.')

        amount = values.get('amount', 0)
        if float_compare(amount, 0, precision_digits=2) <= 0:
            raise UserError('El importe de la reconciliación debe ser mayor que 0.')

        # Facturas y recibos admiten sobrantes. Los movimientos de dinero y las NC no.
        bounded_records = []
        if outgoing_model == 'payment_line':
            bounded_records.append(('pago saliente', outgoing))
        if incoming_model in {'payment_line', 'check', 'credit_note_out'}:
            bounded_records.append(('movimiento entrante', incoming))
        for label, record in bounded_records:
            available = cls._available_amount(record)
            if float_compare(amount, available, precision_digits=2) > 0:
                raise UserError(
                    f'El importe supera el saldo no reconciliado disponible del {label}.'
                )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._validate_reconciliation_values(self.env, values)
        return super().create(vals_list)

    @api.depends('outgoing_move_ref', 'incomming_move_ref')
    def _compute_relational_models_by_references(self):
        for record in self:
            values = {field_name: False for field_name in INCOMMING_FIELDS + OUTGOING_FIELDS}
            outgoing = record.outgoing_move_ref
            incoming = record.incomming_move_ref
            if outgoing and incoming:
                outgoing_field = MODEL_OUT_TO_FIELD.get(outgoing._name)
                incoming_field = MODEL_IN_TO_FIELD.get(incoming._name)
                if outgoing_field and incoming_field:
                    values[outgoing_field] = outgoing.id
                    values[incoming_field] = incoming.id
            record.with_context(workflow_transition=True).write(values)

    @api.depends('confirmed')
    def _compute_auxiliar_is_confirmed(self):
        for record in self:
            record.auxiliar_is_confirmed = 'CONFIRMADA' if record.confirmed else 'PENDIENTE'

    def open_incoming_move(self):
        self.ensure_one()
        if self.check_id:
            model, record = 'check', self.check_id
        elif self.credit_note_out_id:
            model, record = 'credit_note_out', self.credit_note_out_id
        elif self.payment_line_in_id:
            model, record = 'payment_line', self.payment_line_in_id
        else:
            return False
        return {
            'name': record.display_name,
            'view_mode': 'form',
            'res_model': model,
            'res_id': record.id,
            'type': 'ir.actions.act_window',
        }

    def _check_write_permissions_one(self, values):
        if self.confirmed:
            raise UserError('No se puede editar una reconciliación confirmada.')
        ensure_write_allowed_fields(
            self,
            self.env.user,
            values,
            {
                'werlen_repuestos_erp.group_accountant': {'confirmed'},
                'werlen_repuestos_erp.group_sales': {'confirmed'},
                'werlen_repuestos_erp.group_administration': {'confirmed'},
                'werlen_repuestos_erp.group_system': {'*'},
            },
        )

    def write(self, values):
        if self.env.context.get('workflow_transition'):
            return super().write(values)
        for record in self:
            record._check_write_permissions_one(values)
        return super().write(values)

    _sql_constraints = [
        (
            'reconciliation_amount_positive',
            'CHECK(amount > 0)',
            'El importe de la reconciliación debe ser mayor que 0.',
        ),
    ]
