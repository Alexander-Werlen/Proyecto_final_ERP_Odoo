from odoo import fields, models
from odoo.exceptions import ValidationError
from ...utils.group_verification import ensure_user_in_groups

class ResPartner(models.Model):
    _inherit = "res.partner"

    def write(self, vals):
        if 'unique_identifier' in vals:
            protected = self.with_context(active_test=False).filtered(lambda partner: bool(partner.user_ids))
            changed = protected.filtered(lambda partner: vals['unique_identifier'] != partner.unique_identifier)
            if changed:
                raise ValidationError(
                    'El identificador de un contacto asociado a un usuario no puede modificarse.'
                )
        return super().write(vals)

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

    is_supplier = fields.Boolean(
        string='Es proveedor',
        tracking=True,
    )

    is_carrier = fields.Boolean(
        string='Es transportista',
        tracking=True,
    )

    supplier_payment_destination_ids = fields.One2many(
        comodel_name='supplier_payment_destination',
        inverse_name='partner_id',
        string='Destinos de pago',
    )

    def action_open_wizard_current_account_income(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            [
                'werlen_repuestos_erp.group_sales',
                'werlen_repuestos_erp.group_accountant',
            ],
            error_message='Necesitas permisos de Ventas o Caja para registrar ingresos a cuenta corriente.',
        )
        payment_method = self.env.ref(
            'werlen_repuestos_erp.payment_method_efectivo',
            raise_if_not_found=False,
        )
        journal = payment_method.get_default_journal(self.env.user) if payment_method else self.env.user.default_journal_id
        return {
            'name': 'Ingreso a cuenta corriente',
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_current_account_income',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payer_id': self.id,
                'default_payment_method_id': payment_method.id if payment_method else False,
                'default_journal_id': journal.id,
            },
        }

    def action_open_new_check_for_current_account(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            [
                'werlen_repuestos_erp.group_accountant',
                'werlen_repuestos_erp.group_management',
            ],
            error_message='Necesitas permisos de Caja o Gerencia para registrar cheques.',
        )
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
