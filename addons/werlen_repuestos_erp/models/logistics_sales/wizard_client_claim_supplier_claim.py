from odoo import fields, models
from odoo.exceptions import UserError

from ...utils.group_verification import ensure_user_in_groups


CLIENT_CLAIM_SUPPLIER_CLAIM_GROUPS = [
    'werlen_repuestos_erp.group_administration',
]


class WizardClientClaimSupplierClaim(models.TransientModel):
    _name = 'wizard.client.claim.supplier.claim'
    _description = 'Decisión sobre reclamo a proveedor de reclamo de cliente'

    client_claim_id = fields.Many2one(
        'client_claim',
        string='Reclamo de cliente',
        required=True,
        readonly=True,
    )

    client_claim_name = fields.Char(
        related='client_claim_id.name',
        string='Número',
        readonly=True,
    )

    client_name = fields.Char(
        related='client_claim_id.client_name',
        string='Cliente',
        readonly=True,
    )

    def _check_permission(self):
        ensure_user_in_groups(
            self.env.user,
            CLIENT_CLAIM_SUPPLIER_CLAIM_GROUPS,
            error_message='No tiene permisos para decidir sobre el reclamo a proveedor.',
        )

    def _validate_claim(self):
        self.ensure_one()
        if not self.client_claim_id:
            raise UserError('Debe indicar el reclamo de cliente.')
        if self.client_claim_id.state == 'draft':
            raise UserError(
                'El reclamo de cliente debe estar validado antes de decidir sobre '
                'el reclamo a proveedor.'
            )
        if self.client_claim_id.supplier_claim_id:
            raise UserError(
                'El reclamo de cliente ya tiene un reclamo a proveedor asociado.'
            )
        if self.client_claim_id.supplier_claim_not_required:
            raise UserError(
                'Este reclamo ya está marcado como un caso que no se reclamará al proveedor.'
            )
    def action_create_supplier_claim(self):
        self._check_permission()
        self._validate_claim()
        return self.client_claim_id.action_open_wizard_create_supplier_claim()

    def action_mark_supplier_claim_not_required(self):
        self._check_permission()
        self._validate_claim()

        claim = self.client_claim_id
        claim.write({'supplier_claim_not_required': True})
        claim._log_action(
            'No reclamar a proveedor',
            'Se indicó que este reclamo no se reclamará al proveedor ahora ni en el futuro.',
        )
        return {'type': 'ir.actions.act_window_close'}
