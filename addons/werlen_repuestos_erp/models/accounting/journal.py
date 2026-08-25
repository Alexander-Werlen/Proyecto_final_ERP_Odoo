from odoo import fields, models

from ...utils.group_verification import (
    display_warning_toast,
    ensure_user_in_groups,
)


class Journal(models.Model):
    _name = 'journal'
    _description = 'Registro de: Diario/Caja'
    _rec_name = 'name'

    name = fields.Char(string='Diario', required=True)

    allowed_payment_methods = fields.Many2many(
        comodel_name='payment_method',
        relation='payment_method_journal_rel',
        column1='journal_id',
        column2='payment_method_id',
        string='Métodos de pago permitidos',
    )

    cash_sessions = fields.One2many(
        comodel_name='cash_session',
        inverse_name='journal_id',
        string='Sesiones de caja',
    )

    current_cash_session = fields.Many2one(
        comodel_name='cash_session',
        string='Sesión de caja actual',
        ondelete='set null',
    )

    checks = fields.One2many(
        comodel_name='check',
        inverse_name='journal_id',
        string='Cheques',
    )

    allowed_users = fields.Many2many(
        comodel_name='res.users',
        string='Usuarios permitidos para confirmar',
        help='Sólo estos usuarios pueden confirmar movimientos en el diario.',
    )

    def action_manual_in_payment(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja para registrar ingresos.',
        )
        wizard = self.env['wizard_manual_payment_in_journal'].create({
            'journal': self.id,
            'payment_method': self.allowed_payment_methods[:1].id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_manual_payment_in_journal',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_manual_out_payment(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Caja para registrar egresos.',
        )
        wizard = self.env['wizard_manual_payment_out_journal'].create({
            'journal': self.id,
            'payment_method': self.allowed_payment_methods[:1].id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_manual_payment_out_journal',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_create_cash_session(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant'],
            error_message='No tienes permisos para abrir una caja.',
        )

        current_session = self.sudo().current_cash_session
        if current_session and current_session.state == 'open':
            return display_warning_toast(
                title='Caja actualmente abierta',
                message='Ya existe una sesión abierta para este diario.',
            )

        previous_session = self.env['cash_session'].sudo().search(
            [
                ('journal_id', '=', self.id),
                ('state', '=', 'closed'),
            ],
            order='closed_at desc',
            limit=1,
        )
        opening_balance = previous_session.counted_balance if previous_session else 0.0
        session = self.env['cash_session'].sudo().create({
            'journal_id': self.id,
            'previous_session': previous_session.id if previous_session else False,
            'who_is_operating': self.env.user.id,
            'opening_balance': opening_balance,
            'theoretical_balance': opening_balance,
            'counted_balance': 0.0,
            'difference': -opening_balance,
        })
        session._initialize_lines_from_previous_session()
        self.sudo().write({'current_cash_session': session.id})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_open_cash_session_form(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='No tienes permisos para ver el cierre de caja.',
        )
        session = self.sudo().current_cash_session
        if not session:
            return display_warning_toast(
                title='Caja actualmente cerrada',
                message='No hay una sesión abierta para este diario.',
            )
        session.refresh_data()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'cash_session',
            'res_id': session.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def get_dashboard_session_info(self):
        self.ensure_one()
        session = self.sudo().current_cash_session
        if not session or session.state != 'open':
            return {
                'has_open_session': False,
                'is_over_24h': False,
                'hours_open': 0,
                'session_id': False,
            }
        now = fields.Datetime.now()
        hours_open = (now - session.opened_at).total_seconds() / 3600 if session.opened_at else 0
        return {
            'has_open_session': True,
            'is_over_24h': hours_open > 24,
            'hours_open': round(hours_open, 1),
            'session_id': session.id,
        }

    _sql_constraints = [
        (
            'journal_name_uniq',
            'UNIQUE(name)',
            'Ya existe un diario con este nombre.',
        ),
        (
            'journal_name_not_null',
            "CHECK(name IS NOT NULL AND name <> '')",
            'El nombre del diario es obligatorio.',
        ),
    ]
