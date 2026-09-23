from odoo import fields, models
from odoo.exceptions import UserError

from ....utils.group_verification import ensure_user_in_groups


class WizardAddChecksToSupplierPayment(models.TransientModel):
    _name = 'wizard_add_checks_to_supplier_payment'
    _description = 'Asociar cheques a pago a proveedor'

    supplier_payment_id = fields.Many2one(
        comodel_name='supplier_payment', string='Pago a proveedor',
        required=True, readonly=True,
    )
    check_ids = fields.Many2many(
        comodel_name='check', string='Cheques disponibles',
        domain="[('journal_id.name', '!=', 'CHEQUES USADOS'), ('previous_journal_id', '=', False)]",
    )

    def action_confirm(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user, ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para asociar cheques.',
        )
        if not self.check_ids:
            raise UserError('Debe seleccionar al menos un cheque.')
        used_checks_journal = self.env['journal'].search(
            [('name', '=', 'CHEQUES USADOS')], limit=1,
        )
        if not used_checks_journal:
            raise UserError("No existe el diario 'CHEQUES USADOS'. Contacte a administración.")
        for check in self.check_ids:
            if check.previous_journal_id:
                raise UserError(
                    f'El cheque {check.display_name} ya fue usado en otro pago a proveedor.'
                )
            check.write({
                'previous_journal_id': check.journal_id.id,
                'journal_id': used_checks_journal.id,
            })
        self.supplier_payment_id.write({
            'check_ids': [(4, check.id) for check in self.check_ids],
        })
        return {'type': 'ir.actions.act_window_close'}
