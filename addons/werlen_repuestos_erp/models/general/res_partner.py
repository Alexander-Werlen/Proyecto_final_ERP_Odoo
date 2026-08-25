from odoo import fields, models

class ResPartner(models.Model):
    _inherit = "res.partner"

    city_relational_id = fields.Many2one(
        comodel_name="city",
        string="Ciudad",
        tracking=True
    )

    unique_identifier = fields.Char(
        string="Identificador",
        index=True,
        tracking=True
    )

    def action_open_wizard_current_account_income(self):
        self.ensure_one()
        return {
            'name': 'Ingreso a cuenta corriente',
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_current_account_income',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_payer_id': self.id},
        }

    def action_open_new_check_for_current_account(self):
        self.ensure_one()
        return {
            'name': 'Registrar cheque',
            'type': 'ir.actions.act_window',
            'res_model': 'check',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_owner_of_credit': self.id,
                'default_payment_origin_explanation': 'account_in',
            },
        }

    def action_open_pending_account_payments(self):
        self.ensure_one()
        return {
            'name': 'Recibos pendientes',
            'type': 'ir.actions.act_window',
            'res_model': 'account_payment',
            'view_mode': 'list,form',
            'domain': [
                ('client', '=', self.id),
                '|',
                ('payment_status', 'in', ['not_paid', 'partially_paid']),
                ('status', '=', 'draft'),
            ],
        }

    _sql_constraints = [
        (
            'unique_identifier_unique',
            'UNIQUE(unique_identifier)',
            'El identificador de contacto debe ser único para cada contacto.'
        ),
    ]
