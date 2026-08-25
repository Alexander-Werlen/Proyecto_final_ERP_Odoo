from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ...utils.group_verification import ensure_user_in_groups


class CashSessionLine(models.Model):
    _name = 'cash_session_line'
    _description = 'Registro de: Línea de cierre de caja'
    _order = 'category_id'

    cash_session_id = fields.Many2one(
        comodel_name='cash_session',
        required=True,
        ondelete='cascade',
    )
    category_id = fields.Many2one(
        comodel_name='cash_closing_category',
        string='Categoría de cierre',
        required=True,
        ondelete='restrict',
    )
    opening_balance = fields.Monetary(string='Saldo inicial', required=True, default=0.0)
    movements_amount = fields.Monetary(string='Variación del saldo', readonly=True)
    theoretical_balance = fields.Monetary(
        string='Saldo a rendir (teórico)',
        required=True,
        default=0.0,
    )
    counted_balance = fields.Monetary(string='Saldo final', default=0.0)
    difference = fields.Monetary(
        string='Diferencia teórico-final',
        compute='_compute_difference',
        store=True,
    )
    payment_count = fields.Integer(string='Cantidad de movimientos', readonly=True)

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
    confirmed_counted_balance = fields.Boolean(string='Saldo confirmado', default=False)
    confirmed_by = fields.Many2one(
        comodel_name='res.users',
        string='Confirmado por',
        readonly=True,
    )
    confirmed_at = fields.Datetime(string='Fecha de confirmación', readonly=True)

    @api.depends('theoretical_balance', 'counted_balance', 'confirmed_counted_balance')
    def _compute_difference(self):
        for record in self:
            record.difference = (
                record.counted_balance - record.theoretical_balance
                if record.confirmed_counted_balance else 0.0
            )

    def action_open_manual_out_payment_form(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia.',
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_manual_payment_out_journal',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_journal': self.cash_session_id.journal_id.id,
                'default_payment_method': self.category_id.payment_method_ids[:1].id,
                'default_payment_origin_explanation': 'cash_session_closure',
                'default_payee': self.env.company.partner_id.id,
                'default_hide_field_payee': True,
            },
        }

    def write(self, values):
        if self.env.context.get('cash_session_reopen'):
            return super().write(values)
        for record in self:
            if record.cash_session_id.state == 'closed':
                raise ValidationError('No se puede modificar una sesión de caja cerrada.')
        return super().write(values)
