from odoo import models, fields, api
from odoo.exceptions import UserError

from datetime import datetime

from ....utils.group_verification import ensure_user_in_groups

from ....enums.logistics_sales.fulfillment_verification_steps import (
    FULFILLMENT_VERIFICATION_STEP_ENUM
)


class WizardFulfillmentOrderVerification(models.TransientModel):
    _name = 'wizard_fulfillment_order_verification'
    _description = 'Ayudante para: Verificación de orden de venta'

    # ======================================================
    # Control de flujo
    # ======================================================

    current_step = fields.Selection(
        selection=FULFILLMENT_VERIFICATION_STEP_ENUM,
        default='step_1',
        required=True
    )

    # ======================================================
    # Referencias principales
    # ======================================================

    sale_fulfillment_order_id = fields.Many2one(
        comodel_name='sale_fulfillment_order',
        string='Orden de venta',
        required=True
    )

    invoice_id = fields.Many2one(
        comodel_name='invoice_out',
        string='Factura',
        required=True,
        readonly=True
    )

    # ======================================================
    # Datos relacionados (solo lectura)
    # ======================================================

    client = fields.Many2one(
        related='invoice_id.client',
        store=True,
        readonly=True
    )

    full_name = fields.Char(
        related='invoice_id.full_name',
        store=True,
        readonly=True
    )

    company_id = fields.Many2one(
        related='invoice_id.company_id',
        store=True,
        readonly=True
    )

    currency_id = fields.Many2one(
        related='invoice_id.currency_id',
        store=True,
        readonly=True
    )

    total_cost = fields.Monetary(
        related='invoice_id.total_cost',
        store=True,
        readonly=True
    )

    seller = fields.Many2one(
        related='invoice_id.seller',
        store=True,
        readonly=True
    )

    point_of_sale = fields.Many2one(
        'point_of_sale',
        string='Punto de venta',
        default=lambda self: self.env['point_of_sale'].search([('name', 'ilike', 'Mostrador')], limit=1)
    )

    cellphone = fields.Char(
        string='Teléfono'
    )

    is_asigned_to_preparation_team = fields.Boolean(
        string='Preparar al fondo'
    )

    has_delivery = fields.Boolean(
        string='Envío con flete'
    )

    who_withdraws = fields.Many2one(
        'res.partner',
        string='Quién retira'
    )

    destination = fields.Char(
        string='Destino'
    )

    city = fields.Many2one(
        'city',
        string='Ciudad'
    )

    state = fields.Many2one(
        'res.country.state',
        string='Provincia'
    )

    # ======================================================
    # NAVEGACIÓN
    # ======================================================

    def action_next_step(self):
        self.ensure_one()
        self._validate_current_step()

        step_flow = ['step_1', 'step_2', 'step_3', 'step_4']
        current_index = step_flow.index(self.current_step)

        if self.current_step == 'step_2' and not self.has_delivery:
            self._clear_delivery_fields()

        if current_index >= len(step_flow) - 1:
            return False

        self.current_step = step_flow[current_index + 1]
        return self._open_current_step_view()

    def action_previous_step(self):
        self.ensure_one()

        step_flow = ['step_1', 'step_2', 'step_3', 'step_4']
        current_index = step_flow.index(self.current_step)

        if current_index == 0:
            return False

        self.current_step = step_flow[current_index - 1]
        return self._open_current_step_view()

    # ======================================================
    # APERTURA DE VISTAS
    # ======================================================

    def _open_current_step_view(self):
        view_map = {
            'step_1': 'wizard_fulfillment_order_verification_step_1',
            'step_2': 'wizard_fulfillment_order_verification_step_2',
            'step_3': 'wizard_fulfillment_order_verification_step_3',
            'step_4': 'wizard_fulfillment_order_verification_step_4',
        }

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'name': 'Verificación',
            'view_id': self.env.ref(
                f'werlen_repuestos_erp.{view_map[self.current_step]}'
            ).id,
            'target': 'new',
        }

    # ======================================================
    # VALIDACIONES (mínimas)
    # ======================================================

    def _validate_current_step(self):
        # Must Raise error if current step transition is not valid

        if self.current_step == 'step_2' and self.has_delivery:
            if not self.who_withdraws:
                raise UserError("Debe definir quién retira.")
            if not self.destination:
                raise UserError("Debe definir el destino.")
            if not self.city or not self.state:
                raise UserError("Debe definir ciudad y provincia.")

        if self.current_step == 'step_3':
            if not self.point_of_sale:
                raise UserError("Debe definir el punto de venta.")

            if self.point_of_sale and self.point_of_sale.cellphone_required and not self.cellphone:
                raise UserError("Debe definir el teléfono del punto de venta elegido.")

    # ======================================================
    # CONFIRMACIÓN FINAL
    # ======================================================

    def action_confirm(self):
        self.ensure_one()

        """ Update fields of sale_fulfillment_order """
        vals = {
            'logistical_status': 'awaiting_preparation',
            'point_of_sale': self.point_of_sale.id,
            'cellphone': self.cellphone,
            'is_asigned_to_preparation_team': self.is_asigned_to_preparation_team,
            'has_delivery': self.has_delivery,
            'who_withdraws': self.who_withdraws.id,
            'destination': self.destination,
            'city': self.city.id,
            'state': self.state.id,
        }

        self.sale_fulfillment_order_id.sudo().with_context(workflow_transition=True).write(vals)

        self.sale_fulfillment_order_id.with_context(workflow_transition=True).log_action("Verificación finalizada.")

        """ Update fields of client partner info """
        vals = {}

        if not self.client.city_relational_id:
            vals['city_relational_id'] = self.city.id

        if not self.client.street:
            vals['street'] = self.destination

        if not self.client.phone:
            vals['phone'] = self.cellphone

        if vals:
            self.client.sudo().write(vals)

        return {'type': 'ir.actions.act_window_close'}

    def action_skip_verification(self):
        self.ensure_one()
        self._validate_current_step()

        ensure_user_in_groups(
            self.env.user,
            [
            'werlen_repuestos_erp.group_management',
            'werlen_repuestos_erp.group_administration',
            ],
            error_message="Necesitas permisos de Gerencia o Administración para omitir el flujo común de las facturas.",
        )

        """ Update fields of sale_fulfillment_order """
        vals = {
            'logistical_status': 'avoid_tracking',
            'point_of_sale': self.point_of_sale.id,
            'time_of_handing_over': datetime.now(),
        }

        self.sale_fulfillment_order_id.sudo().with_context(workflow_transition=True).write(vals)

        self.sale_fulfillment_order_id.with_context(workflow_transition=True).log_action("Verificación omitida. Esta factura no seguirá el flujo normal.")

    # ======================================================
    # UTILIDADES
    # ======================================================

    def _clear_delivery_fields(self):
        self.who_withdraws = False
        self.destination = False
        self.city = False
        self.state = False
