from datetime import datetime, time

import pytz

from odoo import fields, models


class WizardPaymentLineDaySummary(models.TransientModel):
    _name = 'wizard_payment_line_day_summary'
    _description = 'Ayudante para: Resumen de movimientos por día'

    date = fields.Date(
        string='Día',
        required=True,
        default=fields.Date.context_today,
    )

    def action_open_lines(self):
        self.ensure_one()
        timezone = pytz.timezone('America/Argentina/Buenos_Aires')
        start = timezone.localize(datetime.combine(self.date, time.min)).astimezone(pytz.utc)
        end = timezone.localize(datetime.combine(self.date, time.max)).astimezone(pytz.utc)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Movimientos del día',
            'res_model': 'payment_line',
            'view_mode': 'list,form',
            'domain': [
                ('confirmed', '=', True),
                ('time_of_payment_confirmation', '>=', start),
                ('time_of_payment_confirmation', '<=', end),
            ],
            'context': {
                'search_default_confirmed': 1,
                'group_by': ['journal', 'who_confirmed_payment', 'payment_origin_explanation'],
            },
        }
