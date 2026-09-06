from odoo import api, fields, models
from odoo.exceptions import UserError

from ....utils.group_verification import display_warning_toast, ensure_user_in_groups


class WizardCreateCreditNoteOut(models.TransientModel):
    _name = 'wizard_create_credit_note_out'
    _description = 'Ayudante para: Crear nota de crédito emitida'

    credit_note_id = fields.Char(string='Número', required=True)
    invoice_type = fields.Many2one(
        'invoice_type',
        string='Tipo',
        required=True,
        domain="[('invoice_type_id', '=like', 'NC-%')]",
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    client = fields.Many2one('res.partner', string='Propietario del crédito', required=True)
    full_name = fields.Char(string='Nombre del propietario')
    total_amount = fields.Monetary(string='Importe', required=True)
    seller_of_related_invoice = fields.Many2one(
        'res.users',
        string='Vendedor de la factura origen',
        default=lambda self: self.env.user,
        required=True,
    )
    date = fields.Datetime(string='Fecha de emisión', default=fields.Datetime.now, required=True)
    payment_method = fields.Many2one(
        'payment_method',
        string='Condición de venta',
        required=True,
        default=lambda self: self.env.ref(
            'werlen_repuestos_erp.payment_method_efectivo',
            raise_if_not_found=False,
        ),
    )

    @api.onchange('client')
    def _onchange_client(self):
        for record in self:
            if record.client:
                record.full_name = record.client.name

    def action_confirm_draft(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_sales'],
            error_message='Necesitas permisos de Ventas para crear notas de crédito.',
        )
        if self.total_amount <= 0:
            return display_warning_toast('Importe inválido', 'El importe debe ser mayor que 0.')
        if not self.full_name:
            return display_warning_toast('Nombre faltante', 'Debe indicar el nombre del propietario.')
        full_id = f'{self.invoice_type.invoice_type_id}-{self.credit_note_id}'
        if self.env['credit_note_out'].search_count([('credit_note_id', '=', full_id)]):
            raise UserError(f'Ya existe una nota de crédito con identificador {full_id}.')
        record = self.env['credit_note_out'].create({
            'credit_note_id': full_id,
            'invoice_type': self.invoice_type.id,
            'client': self.client.id,
            'full_name': self.full_name,
            'total_amount': self.total_amount,
            'seller_of_related_invoice': self.seller_of_related_invoice.id,
            'date': self.date,
            'payment_method': self.payment_method.id,
            'is_manual_invoice': True,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'credit_note_out',
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }
