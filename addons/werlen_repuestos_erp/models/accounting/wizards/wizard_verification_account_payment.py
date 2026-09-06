from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ....utils.group_verification import display_warning_toast, ensure_user_in_groups


class WizardVerificationAccountPayment(models.TransientModel):
    _name = 'wizard_verification_account_payment'
    _description = 'Ayudante para: Verificar recibo'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    account_payment = fields.Many2one('account_payment', string='Recibo', required=True, readonly=True)
    client = fields.Many2one('res.partner', string='Cliente', required=True, readonly=True)
    amount = fields.Monetary(string='Importe', required=True, readonly=True)
    discount_amount = fields.Monetary(string='Descuento', required=True, readonly=True)
    date = fields.Datetime(string='Fecha', required=True, readonly=True)
    who_created = fields.Many2one('res.users', string='Creador', required=True)
    observations = fields.Text(string='Observaciones')
    previous_amount_reconciliated = fields.Monetary(string='Importe reconciliado previo', readonly=True)
    amount_reconciliated = fields.Monetary(
        string='Importe reconciliado',
        compute='_compute_amounts',
    )
    amount_not_reconciliated = fields.Monetary(
        string='Importe no reconciliado',
        compute='_compute_amounts',
    )
    related_payments = fields.Many2many(
        'payment_line',
        string='Pagos asociados',
        domain="[('payer', '=', client), ('payment_origin_explanation', '=', 'account_in'), ('payment_status', 'in', ['not_paid', 'partially_paid'])]",
    )
    related_checks = fields.Many2many(
        'check',
        string='Cheques asociados',
        domain="[('owner_of_credit', '=', client), ('payment_status', 'in', ['not_paid', 'partially_paid'])]",
    )

    @api.depends('related_payments', 'related_checks', 'previous_amount_reconciliated')
    def _compute_amounts(self):
        for record in self:
            total = record.previous_amount_reconciliated
            total += sum(record.related_payments.mapped('amount_not_reconciliated'))
            total += sum(record.related_checks.mapped('amount_not_reconciliated'))
            record.amount_reconciliated = total
            record.amount_not_reconciliated = record.amount - total

    def _validate_verification_values(self):
        self.ensure_one()
        if not self.account_payment:
            raise UserError('Debe indicar el recibo a verificar.')
        if self.account_payment.client != self.client:
            raise UserError('El cliente del wizard no coincide con el recibo.')
        if float_compare(self.account_payment.amount, self.amount, precision_digits=2) != 0:
            raise UserError('El importe del wizard no coincide con el recibo.')
        if float_compare(
            self.account_payment.discount_amount,
            self.discount_amount,
            precision_digits=2,
        ) != 0:
            raise UserError('El descuento del wizard no coincide con el recibo.')
        if (
            self.account_payment.who_created
            and self.who_created
            and self.account_payment.who_created != self.who_created
        ):
            raise UserError('El creador del wizard no coincide con el recibo.')
        if float_compare(
            self.account_payment.amount_reconciliated_unconfirmed,
            self.previous_amount_reconciliated,
            precision_digits=2,
        ) != 0:
            raise UserError('El saldo reconciliado del recibo cambió; vuelva a abrir el wizard.')

        for payment in self.related_payments:
            if payment.is_outgoing:
                raise UserError('Los pagos asociados deben ser movimientos entrantes.')
            if (
                payment.payer != self.client
                or payment.payment_origin_explanation != 'account_in'
            ):
                raise UserError(
                    'Los pagos seleccionados deben ser ingresos a cuenta corriente del cliente.'
                )
            if payment.company_id != self.company_id:
                raise UserError('El pago seleccionado pertenece a otra compañía.')

        for check in self.related_checks:
            if check.owner_of_credit != self.client:
                raise UserError(
                    'Los cheques seleccionados deben pertenecer al cliente del recibo.'
                )
            if check.company_id != self.company_id:
                raise UserError('El cheque seleccionado pertenece a otra compañía.')

        if self.amount_reconciliated < 0:
            raise UserError('El importe reconciliado no puede ser negativo.')

    def action_confirm_verification(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para verificar recibos.',
        )
        if not self.who_created:
            return display_warning_toast('Datos faltantes', 'Debe indicar quién emitió el recibo.')
        if self.account_payment.status != 'draft':
            return display_warning_toast('Recibo ya verificado', 'El recibo ya fue verificado.')
        self._validate_verification_values()
        self.account_payment.sudo().write({
            'who_created': self.who_created.id,
            'status': 'verified',
            'observations': self.observations,
        })
        for payment in self.related_payments:
            if not payment.confirmed:
                payment.confirm_payment()
            amount = payment.get_amount_not_reconciliated()
            if amount <= 0:
                continue
            self.env['reconciliation_line'].create({
                'outgoing_move_ref': f'account_payment,{self.account_payment.id}',
                'incomming_move_ref': f'payment_line,{payment.id}',
                'amount': amount,
                'confirmed': True,
            })
        for check in self.related_checks:
            amount = check.get_amount_not_reconciliated()
            if amount <= 0:
                continue
            self.env['reconciliation_line'].create({
                'outgoing_move_ref': f'account_payment,{self.account_payment.id}',
                'incomming_move_ref': f'check,{check.id}',
                'amount': amount,
                'confirmed': True,
            })
        return {'type': 'ir.actions.act_window_close'}
