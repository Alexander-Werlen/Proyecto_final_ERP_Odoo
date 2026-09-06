from odoo import fields, models
from odoo.exceptions import ValidationError

from ....utils.group_verification import ensure_user_in_groups


class WizardCloseCashSession(models.TransientModel):
    _name = 'wizard_close_cash_session'
    _description = 'Wizard de cierre de caja'

    cash_session_id = fields.Many2one(
        'cash_session',
        string='Sesión de caja',
        required=True,
        readonly=True,
    )
    journal_id = fields.Many2one(related='cash_session_id.journal_id', readonly=True)
    currency_id = fields.Many2one(related='cash_session_id.currency_id', readonly=True)
    line_ids = fields.One2many(
        'wizard_close_cash_session_line',
        'wizard_id',
        string='Categorías',
    )

    def _populate_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        for line in self.cash_session_id.line_ids:
            self.env['wizard_close_cash_session_line'].create({
                'wizard_id': self.id,
                'cash_session_line_id': line.id,
                'counted_balance': line.counted_balance,
            })

    def action_confirm_close(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para cerrar la caja.',
        )
        if self.cash_session_id.state != 'open':
            raise ValidationError('La sesión de caja ya está cerrada.')
        for line in self.line_ids:
            if line.counted_balance < 0:
                raise ValidationError(
                    f"El saldo final de '{line.category_id.name}' no puede ser negativo."
                )
        for line in self.line_ids:
            line.cash_session_line_id.write({
                'counted_balance': line.counted_balance,
                'confirmed_counted_balance': True,
                'confirmed_by': self.env.user.id,
                'confirmed_at': fields.Datetime.now(),
            })
        self.cash_session_id.action_close_cash_session()
        return {'type': 'ir.actions.act_window_close'}
