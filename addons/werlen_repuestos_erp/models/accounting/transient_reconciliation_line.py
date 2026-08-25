from odoo import api, fields, models

from ...enums.accounting.reconciliation_fields import INCOMMING_MODELS, OUTGOING_MODELS
from ...utils.group_verification import display_warning_toast, ensure_user_in_groups


class TransientReconciliationLine(models.TransientModel):
    _name = 'transient_reconciliation_line'
    _description = 'Ayudante para: Crear línea de reconciliación'

    amount = fields.Monetary(string='Importe a reconciliar', required=True, default=0.0)
    confirmed = fields.Boolean(string='Confirmada', default=False)

    outgoing_move_ref = fields.Reference(selection=OUTGOING_MODELS, string='Movimiento saliente')
    incomming_move_ref = fields.Reference(selection=INCOMMING_MODELS, string='Movimiento entrante')

    outgoing_move_amount_not_reconciliated = fields.Monetary(
        string='Importe pendiente saliente',
        compute='_compute_pending_amounts',
    )
    incomming_move_amount_not_reconciliated = fields.Monetary(
        string='Importe pendiente entrante',
        compute='_compute_pending_amounts',
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Moneda',
        required=True,
    )

    @api.depends('outgoing_move_ref', 'incomming_move_ref')
    def _compute_pending_amounts(self):
        for line in self:
            line.outgoing_move_amount_not_reconciliated = (
                line.outgoing_move_ref.get_amount_not_reconciliated()
                if line.outgoing_move_ref else 0.0
            )
            line.incomming_move_amount_not_reconciliated = (
                line.incomming_move_ref.get_amount_not_reconciliated()
                if line.incomming_move_ref else 0.0
            )

    @api.onchange('outgoing_move_ref', 'incomming_move_ref')
    def _onchange_set_amount_to_min_pending(self):
        for line in self:
            if line.outgoing_move_ref and line.incomming_move_ref:
                line.amount = min(
                    line.outgoing_move_ref.get_amount_not_reconciliated(),
                    line.incomming_move_ref.get_amount_not_reconciliated(),
                )

    def create_manual_reconciliation_line(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_administration', 'werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja o Administración para reconciliar manualmente.',
        )
        if self.amount <= 0:
            return display_warning_toast(
                title='Importe inválido',
                message='El importe debe ser mayor que 0.',
            )
        if not self.outgoing_move_ref or not self.incomming_move_ref:
            return display_warning_toast(
                title='Movimientos incompletos',
                message='Debe seleccionar un movimiento saliente y uno entrante.',
            )
        confirmed = (
            self.incomming_move_ref._name != 'payment_line'
            or self.incomming_move_ref.confirmed
        )
        self.env['reconciliation_line'].create({
            'outgoing_move_ref': f'{self.outgoing_move_ref._name},{self.outgoing_move_ref.id}',
            'incomming_move_ref': f'{self.incomming_move_ref._name},{self.incomming_move_ref.id}',
            'amount': self.amount,
            'confirmed': confirmed,
        })
        return True
