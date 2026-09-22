from odoo import fields, models

from ....utils.group_verification import ensure_user_in_groups, display_warning_toast


class WizardCreateReception(models.TransientModel):
    _name = 'wizard_create_reception'
    _description = 'Wizard para crear un ingreso de mercadería'

    reception_datetime = fields.Datetime(
        string='Fecha y hora de recepción',
        required=True,
        default=fields.Datetime.now,
    )
    supplier_id = fields.Many2one(
        'res.partner', string='Proveedor', required=True,
        domain=[('is_supplier', '=', True)],
    )
    carrier_id = fields.Many2one(
        'res.partner', string='Transportista', required=True,
        domain=[('is_carrier', '=', True)],
    )
    packages_description = fields.Char(
        string='Bultos', required=True,
        help='Descripción de la cantidad y tipo de bultos o pallets recibidos.',
    )
    remito_number = fields.Char(string='Número de remito')
    observations = fields.Text(string='Observaciones')
    who_received_ids = fields.Many2many(
        'res.users',
        string='Empleados que recibieron',
        required=True,
        default=lambda self: [(6, 0, [self.env.user.id])],
    )

    def _validate_inputs(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_reception'],
            error_message='No tiene permisos para crear ingresos de mercadería.',
        )
        if not self.who_received_ids:
            return display_warning_toast(
                title='Empleados faltantes',
                message='Debe indicar al menos un empleado que recibió la mercadería.',
            )
        if not self.packages_description or not self.packages_description.strip():
            return display_warning_toast(
                title='Bultos faltantes',
                message='Debe ingresar una descripción de los bultos recibidos.',
            )
        if not self.supplier_id:
            return display_warning_toast(
                title='Proveedor faltante',
                message='Debe seleccionar un proveedor.',
            )
        if not self.carrier_id:
            return display_warning_toast(
                title='Transportista faltante',
                message='Debe seleccionar un transportista.',
            )
        return None

    def action_create_reception(self):
        self.ensure_one()
        warning = self._validate_inputs()
        if warning:
            return warning
        self.env['reception'].create({
            'reception_datetime': self.reception_datetime,
            'supplier_id': self.supplier_id.id,
            'carrier_id': self.carrier_id.id,
            'packages_description': self.packages_description.strip(),
            'remito_number': (self.remito_number or '').strip() or False,
            'observations': (self.observations or '').strip() or False,
            'who_received_ids': [(6, 0, self.who_received_ids.ids)],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ingresos',
            'res_model': 'reception',
            'view_mode': 'list,form',
            'view_ids': [
                (5, 0, 0),
                (0, 0, {
                    'view_mode': 'list',
                    'view_id': self.env.ref('werlen_repuestos_erp.reception_list_view').id,
                }),
                (0, 0, {
                    'view_mode': 'form',
                    'view_id': self.env.ref('werlen_repuestos_erp.reception_form_view').id,
                }),
            ],
            'search_view_id': self.env.ref('werlen_repuestos_erp.reception_search_view').id,
            'context': {'search_default_pending_review': 1},
        }
