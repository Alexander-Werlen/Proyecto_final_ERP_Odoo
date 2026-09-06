from odoo import fields, models

from ....utils.group_verification import ensure_user_in_groups


class WizardChangeCheckJournal(models.TransientModel):
    _name = 'wizard_change_check_journal'
    _description = 'Ayudante para: Cambiar diario de cheque'

    check_id = fields.Many2one('check', string='Cheque', required=True, readonly=True)
    check_amount = fields.Monetary(related='check_id.amount', string='Importe', readonly=True)
    current_journal_id = fields.Many2one('journal', string='Diario actual', readonly=True)
    new_journal_id = fields.Many2one('journal', string='Nuevo diario', required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')

    def action_confirm(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para cambiar el diario.',
        )
        self.check_id.sudo().write({
            'previous_journal_id': self.check_id.journal_id.id,
            'journal_id': self.new_journal_id.id,
        })
        return {'type': 'ir.actions.act_window_close'}
