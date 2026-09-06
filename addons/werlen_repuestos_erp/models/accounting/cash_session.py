from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ...utils.group_verification import (
    display_warning_toast,
    ensure_user_in_groups,
    ensure_write_allowed_fields,
)


class CashSession(models.Model):
    _name = 'cash_session'
    _description = 'Registro de: Sesión de caja/diario'
    _order = 'opened_at desc'

    name = fields.Char(string='Cierre de caja/diario', readonly=True)
    previous_session = fields.Many2one(
        comodel_name='cash_session',
        string='Cierre previo',
        readonly=True,
        ondelete='set null',
    )
    journal_id = fields.Many2one(
        comodel_name='journal',
        string='Caja/Diario',
        required=True,
        ondelete='restrict',
    )
    who_is_operating = fields.Many2one(
        comodel_name='res.users',
        string='Responsable',
    )
    state = fields.Selection(
        selection=[('open', 'Abierta'), ('closed', 'Cerrada')],
        string='Estado',
        required=True,
        default='open',
        index=True,
    )
    opening_balance = fields.Monetary(string='Saldo total inicial', readonly=True, default=0.0)
    opened_at = fields.Datetime(
        string='Fecha de apertura',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    closed_at = fields.Datetime(string='Fecha de cierre', readonly=True)
    theoretical_balance = fields.Monetary(string='Saldo total a rendir (teórico)', readonly=True)
    counted_balance = fields.Monetary(string='Saldo total final', readonly=True)
    difference = fields.Monetary(string='Diferencia teórico-final', readonly=True)
    displayed_difference = fields.Monetary(
        string='Diferencia mostrada',
        compute='_compute_displayed_difference',
        store=True,
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
    line_ids = fields.One2many(
        comodel_name='cash_session_line',
        inverse_name='cash_session_id',
        string='Movimientos por categoría',
        readonly=True,
    )
    checks = fields.One2many(
        related='journal_id.checks',
        string='Cheques del diario',
    )
    who_closed = fields.Many2one(
        comodel_name='res.users',
        string='Quién validó el cierre',
        readonly=True,
    )
    last_refresh_at = fields.Datetime(string='Última actualización', readonly=True)
    observations = fields.Text(string='Observaciones')
    withdrawal_ids = fields.Many2many(
        comodel_name='payment_line',
        compute='_compute_withdrawal_ids',
        string='Retiros de esta sesión',
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            ensure_user_in_groups(
                self.env.user,
                ['werlen_repuestos_erp.group_accountant'],
                error_message='Necesitas permisos de Caja para abrir una sesión.',
            )
        for values in vals_list:
            if values.get('state', 'open') != 'open' and not self.env.su:
                raise ValidationError('Las sesiones nuevas deben comenzar abiertas.')
            values.setdefault('state', 'open')
            if not self.env.su:
                values['who_is_operating'] = self.env.user.id
        records = super().create(vals_list)
        for record in records:
            if not record.name:
                record.name = f'{record.journal_id.name} - {record.opened_at}'
        return records

    def _initialize_lines_from_previous_session(self):
        self.ensure_one()
        if not self.previous_session:
            return
        for previous_line in self.previous_session.line_ids:
            opening = previous_line.counted_balance or 0.0
            if not opening:
                continue
            self.env['cash_session_line'].create({
                'cash_session_id': self.id,
                'category_id': previous_line.category_id.id,
                'opening_balance': opening,
                'theoretical_balance': opening,
            })

    @api.depends('journal_id', 'opened_at', 'closed_at', 'state', 'previous_session')
    def _compute_withdrawal_ids(self):
        for session in self:
            if not session.journal_id:
                session.withdrawal_ids = False
                continue
            domain = [
                ('journal', '=', session.journal_id.id),
                ('is_outgoing', '=', True),
                ('payment_origin_explanation', '=', 'cash_session_closure'),
                ('confirmed', '=', True),
                ('time_of_payment_confirmation', '>=', session.opened_at),
            ]
            if session.closed_at:
                domain.append(('time_of_payment_confirmation', '<=', session.closed_at))
            session.withdrawal_ids = self.env['payment_line'].search(domain)

    def _get_payment_date_range(self):
        self.ensure_one()
        return self.opened_at, fields.Datetime.now()

    def _recompute_totals(self):
        for session in self:
            theoretical = sum(session.line_ids.mapped('theoretical_balance'))
            confirmed_lines = session.line_ids.filtered('confirmed_counted_balance')
            counted = sum(confirmed_lines.mapped('counted_balance')) if confirmed_lines else 0.0
            session.sudo().write({
                'theoretical_balance': theoretical,
                'counted_balance': counted,
                'difference': counted - theoretical,
            })

    @api.depends('state', 'counted_balance', 'theoretical_balance')
    def _compute_displayed_difference(self):
        for session in self:
            session.displayed_difference = (
                session.counted_balance - session.theoretical_balance
                if session.state == 'closed' else 0.0
            )

    def refresh_data(self):
        self.ensure_one()
        if self.state != 'open':
            return display_warning_toast(
                title='Acción no permitida',
                message='Sólo se puede actualizar una sesión abierta.',
            )

        date_from, date_to = self._get_payment_date_range()
        PaymentLine = self.env['payment_line']
        existing = {line.category_id.id: line for line in self.line_ids}
        categories = self.env['cash_closing_category'].search([('active_currently', '=', True)])

        for category in categories:
            method_ids = category.payment_method_ids.ids
            if not method_ids:
                continue
            domain = [
                ('journal', '=', self.journal_id.id),
                ('confirmed', '=', True),
                ('payment_method', 'in', method_ids),
                ('time_of_payment_confirmation', '>=', date_from),
                ('time_of_payment_confirmation', '<=', date_to),
            ]
            incoming = PaymentLine.search(domain + [('is_outgoing', '=', False)])
            outgoing = PaymentLine.search(domain + [('is_outgoing', '=', True)])
            movements = sum(incoming.mapped('amount')) - sum(outgoing.mapped('amount'))
            opening = existing[category.id].opening_balance if category.id in existing else 0.0
            values = {
                'movements_amount': movements,
                'theoretical_balance': opening + movements,
                'payment_count': len(incoming | outgoing),
            }
            if category.id in existing:
                existing[category.id].sudo().write(values)
            elif opening or movements or values['payment_count']:
                self.env['cash_session_line'].create({
                    'cash_session_id': self.id,
                    'category_id': category.id,
                    'opening_balance': opening,
                    **values,
                })

        self._recompute_totals()
        self.sudo().write({
            'last_refresh_at': fields.Datetime.now(),
        })
        return True

    def action_open_close_wizard(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para cerrar la caja.',
        )
        if self.state != 'open':
            raise ValidationError('La sesión ya está cerrada.')
        wizard = self.env['wizard_close_cash_session'].create({'cash_session_id': self.id})
        wizard._populate_lines()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_close_cash_session',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_close_cash_session(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para cerrar la caja.',
        )
        self.refresh_data()
        if self.state != 'open':
            raise ValidationError('La sesión de caja ya está cerrada.')
        if self.line_ids.filtered(lambda line: not line.confirmed_counted_balance):
            raise ValidationError('No se puede cerrar la caja: existen categorías sin confirmar.')
        self._recompute_totals()
        self.sudo().write({
            'state': 'closed',
            'closed_at': fields.Datetime.now(),
            'who_closed': self.env.user.id,
        })
        self.journal_id.sudo().write({'current_cash_session': False})
        return True

    def action_reopen_cash_session(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para reabrir la caja.',
        )
        if self.state != 'closed':
            raise ValidationError('La sesión no está cerrada.')
        latest = self.env['cash_session'].search(
            [('journal_id', '=', self.journal_id.id), ('state', '=', 'closed')],
            order='closed_at desc',
            limit=1,
        )
        if latest != self:
            raise ValidationError('Sólo se puede reabrir el último cierre de esta caja.')
        self.line_ids.sudo().write({
            'confirmed_counted_balance': False,
            'confirmed_by': False,
            'confirmed_at': False,
            'counted_balance': 0.0,
        })
        self.sudo().write({
            'state': 'open',
            'closed_at': False,
            'who_closed': False,
        })
        self.journal_id.sudo().write({'current_cash_session': self.id})
        return True

    def write(self, values):
        if self.env.su:
            return super().write(values)
        for record in self:
            if record.state == 'closed':
                raise ValidationError('No se puede modificar una caja cerrada.')
            ensure_write_allowed_fields(
                record,
                self.env.user,
                values,
                {
                    'werlen_repuestos_erp.group_accountant': {'observations'},
                    'werlen_repuestos_erp.group_management': {'observations'},
                    'werlen_repuestos_erp.group_system': {'*'},
                },
            )
        return super().write(values)
