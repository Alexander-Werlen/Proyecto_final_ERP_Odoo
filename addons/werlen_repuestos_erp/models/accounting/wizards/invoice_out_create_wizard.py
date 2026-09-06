from odoo import models, fields, api

from ....utils.group_verification import display_warning_toast, ensure_user_in_groups

class InvoiceOutCreateWizard(models.TransientModel):
    _name = 'invoice_out_create_wizard'
    _description = 'Wizard para crear facturas manuales'

    invoice_id = fields.Char(
        string='Número', 
        required=True,
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param('werlen_repuestos_erp.param_manual_invoice_point_of_sale') or '0020-'
    )

    invoice_type = fields.Many2one(
        'invoice_type',
        string='Tipo',
        required=True
    )

    client = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True
    )

    full_name = fields.Char(string='Nombre completo')

    total_cost = fields.Monetary(
        string='Importe',
        required=True
    )

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.user.company_id.id
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id'
    )

    payment_method = fields.Many2one(
        'payment_method',
        string='Cond. Venta',
        required=True
    )

    seller = fields.Many2one(
        'res.users',
        string="Vendedor",
        default=lambda self: self.env.user,
        required=True
    )

    date = fields.Datetime(
        string='Fecha',
        default=fields.Datetime.now
    )

    @api.onchange('client')
    def _onchange_client(self):
        if self.client:
            self.full_name = self.client.name

    # === Acción principal ===

    def action_create_invoice(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_sales'],
            error_message='Necesitas permisos de Ventas para crear facturas.',
        )

        if self.total_cost <= 0:
            return display_warning_toast(
                title="Monto Invalido",
                message="El monto debe ser mayor a 0.",
            )

        #Check it isnt just the default id
        if self.invoice_id == self.env['ir.config_parameter'].sudo().get_param('werlen_repuestos_erp.param_manual_invoice_point_of_sale') or self.invoice_id == '0020-':
            return display_warning_toast(
                title="Número de Factura Invalido",
                message="El número de factura solo contiene el prefijo. Especificar número completo",
            )

        invoice_vals = {
            'invoice_id': f"{self.invoice_type.invoice_type_id}-{self.invoice_id}",
            'invoice_type': self.invoice_type.id,
            'client': self.client.id,
            'full_name': self.full_name,
            'total_cost': self.total_cost,
            'payment_method': self.payment_method.id,
            'seller': self.seller.id,
            'date': self.date,
            'is_draft': True,
            'is_manual_invoice': True,
        }

        invoice = self.env['invoice_out'].create(invoice_vals)

        invoice.confirm_draft()

        #Search and Open fulfillment order where invoice_id is the one we just created

        fulfillment_order = self.env['sale_fulfillment_order'].search([('invoice_id', '=', invoice.id)]).id

        if fulfillment_order:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale_fulfillment_order',
                'view_mode': 'form',
                'res_id': fulfillment_order,
                'target': 'current',
            }
