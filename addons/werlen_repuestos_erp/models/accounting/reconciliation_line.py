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

    @staticmethod
    def _movement_partner(model_name, record):
        if model_name in {'invoice_out', 'account_payment', 'credit_note_out'}:
            return record.client
        if model_name == 'payment_line':
            return record.payee if record.is_outgoing else record.payer
        if model_name == 'check':
            return record.owner_of_credit
        return False

    @classmethod
    def _validate_reconciliation_values(cls, env, values, current_line=None):
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

        outgoing_company = getattr(outgoing, 'company_id', False)
        incoming_company = getattr(incoming, 'company_id', False)
        if outgoing_company and incoming_company and outgoing_company != incoming_company:
            raise UserError('Los movimientos deben pertenecer a la misma compañía.')

        outgoing_currency = getattr(outgoing, 'currency_id', False)
        incoming_currency = getattr(incoming, 'currency_id', False)
        if outgoing_currency and incoming_currency and outgoing_currency != incoming_currency:
            raise UserError('Los movimientos deben utilizar la misma moneda.')

        outgoing_partner = cls._movement_partner(outgoing_model, outgoing)
        incoming_partner = cls._movement_partner(incoming_model, incoming)
        if outgoing_partner and incoming_partner and outgoing_partner != incoming_partner:
            raise UserError('Los movimientos deben pertenecer al mismo cliente.')

        if outgoing_model == 'account_payment' and incoming_model not in {'payment_line', 'check'}:
            raise UserError('Los recibos sólo se pueden reconciliar con pagos y cheques.')
        if outgoing_model == 'invoice_out' and getattr(outgoing, 'is_account_move', False):
            raise UserError('Las facturas de cuenta corriente no se pueden reconciliar.')
        if outgoing_model == 'invoice_out' and outgoing.is_draft:
            raise UserError('Las facturas en borrador no se pueden reconciliar.')
        if incoming_model == 'credit_note_out':
            if getattr(incoming, 'is_account_move', False):
                raise UserError('Las notas de crédito de cuenta corriente no se pueden reconciliar.')
            if incoming.state != 'verified':
                raise UserError('Sólo se pueden usar notas de crédito verificadas.')
        if values.get('confirmed') and incoming_model == 'payment_line' and not incoming.confirmed:
            raise UserError('No se puede confirmar una reconciliación con un pago no confirmado.')

        amount = values.get('amount', 0)
        if float_compare(amount, 0, precision_digits=2) <= 0:
            raise UserError('El importe de la reconciliación debe ser mayor que 0.')

        # Facturas y recibos admiten sobrantes. Los movimientos de dinero y las NC no.
        bounded_records = []
        if outgoing_model == 'payment_line':
            bounded_records.append(('pago saliente', outgoing_model, outgoing))
        if incoming_model in {'payment_line', 'check', 'credit_note_out'}:
            bounded_records.append(('movimiento entrante', incoming_model, incoming))
        for label, model_name, movement in bounded_records:
            available = cls._available_amount(movement)
            if current_line:
                existing_move = (
                    current_line.outgoing_move_ref
                    if label == 'pago saliente'
                    else current_line.incomming_move_ref
                )
                if (
                    existing_move
                    and existing_move._name == model_name
                    and existing_move.id == movement.id
                ):
                    available += current_line.amount
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
            for field_name, value in values.items():
                record[field_name] = value

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
        for record in self:
            record._check_write_permissions_one(values)
            if any(
                field_name in values
                for field_name in ('outgoing_move_ref', 'incomming_move_ref', 'amount', 'confirmed')
            ):
                outgoing = values.get('outgoing_move_ref', record.outgoing_move_ref)
                incoming = values.get('incomming_move_ref', record.incomming_move_ref)
                self._validate_reconciliation_values(self.env, {
                    'outgoing_move_ref': (
                        outgoing
                        if isinstance(outgoing, str)
                        else f'{outgoing._name},{outgoing.id}' if outgoing else False
                    ),
                    'incomming_move_ref': (
                        incoming
                        if isinstance(incoming, str)
                        else f'{incoming._name},{incoming.id}' if incoming else False
                    ),
                    'amount': values.get('amount', record.amount),
                    'confirmed': values.get('confirmed', record.confirmed),
                }, current_line=record)
        return super().write(values)

    _sql_constraints = [
        (
            'reconciliation_amount_positive',
            'CHECK(amount > 0)',
            'El importe de la reconciliación debe ser mayor que 0.',
        ),
    ]
