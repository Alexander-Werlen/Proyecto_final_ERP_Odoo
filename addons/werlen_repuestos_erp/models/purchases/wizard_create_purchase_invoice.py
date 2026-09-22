from odoo import fields, models

from ...utils.group_verification import ensure_user_in_groups, display_warning_toast


class WizardCreatePurchaseInvoice(models.TransientModel):
    _name = 'wizard_create_purchase_invoice'
    _description = 'Wizard para crear una factura de compra'

    name = fields.Char(string='Número', required=True)
    supplier_id = fields.Many2one(
        'res.partner', string='Proveedor', required=True,
        domain=[('is_supplier', '=', True)],
    )

    def _validate_inputs(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            [
                'werlen_repuestos_erp.group_reception_control',
                'werlen_repuestos_erp.group_administration',
            ],
            error_message='No tiene permisos para crear facturas de compra.',
        )
        if not self.name or not self.name.strip():
            return display_warning_toast(
                title='Número faltante',
                message='Debe ingresar el número de la factura de compra.',
            )
        if not self.supplier_id:
            return display_warning_toast(
                title='Proveedor faltante',
                message='Debe seleccionar un proveedor.',
            )
        if self.env['purchase_invoice'].search([
            ('name', '=', self.name.strip()),
            ('supplier_id', '=', self.supplier_id.id),
        ], limit=1):
            return display_warning_toast(
                title='Factura duplicada',
                message=f'Ya existe la factura {self.name.strip()} para el proveedor {self.supplier_id.name}.',
            )
        return None

    def action_create_purchase_invoice(self):
        self.ensure_one()
        warning = self._validate_inputs()
        if warning:
            return warning
        invoice = self.env['purchase_invoice'].create({
            'name': self.name.strip(),
            'supplier_id': self.supplier_id.id,
            'state': 'pending_delivery',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Factura de compra',
            'res_model': 'purchase_invoice',
            'view_mode': 'form',
            'res_id': invoice.id,
            'view_id': self.env.ref('werlen_repuestos_erp.purchase_invoice_form_view').id,
            'target': 'current',
        }
