from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ....utils.group_verification import display_warning_toast, ensure_user_in_groups


class WizardVerificationCreditNoteOut(models.TransientModel):
    _name = 'wizard_verification_credit_note_out'
    _description = 'Ayudante para: Verificar nota de crédito emitida'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    credit_note = fields.Many2one('credit_note_out', string='Nota de crédito', required=True, readonly=True)
    credit_note_id = fields.Char(string='Número NC', readonly=True)
    client = fields.Many2one('res.partner', string='Propietario del crédito', readonly=True)
    full_name = fields.Char(string='Nombre del propietario', readonly=True)
    total_amount = fields.Monetary(string='Importe', readonly=True)
    seller_of_related_invoice = fields.Many2one('res.users', string='Vendedor', readonly=True)
    date = fields.Datetime(string='Fecha de emisión', readonly=True)
    skip_related_invoice = fields.Boolean(string='Omitir factura origen', default=False)
    related_invoice = fields.Many2one('invoice_out', string='Factura origen')
    observations = fields.Text(string='Observaciones')
    who_approved = fields.Many2one(
        'res.users',
        string='Aprobado por',
        default=lambda self: self.env.user,
    )
    who_created = fields.Many2one('res.users', string='Emitida por')

    def _validate_verification_values(self):
        self.ensure_one()
        note = self.credit_note
        if not note:
            raise UserError('Debe indicar la nota de crédito a verificar.')
        if self.credit_note_id != note.credit_note_id:
            raise UserError('El identificador del wizard no coincide con la nota de crédito.')
        if self.client != note.client:
            raise UserError('El cliente del wizard no coincide con la nota de crédito.')
        if float_compare(self.total_amount, note.total_amount, precision_digits=2) != 0:
            raise UserError('El importe del wizard no coincide con la nota de crédito.')
        if self.seller_of_related_invoice != note.seller_of_related_invoice:
            raise UserError('El vendedor del wizard no coincide con la nota de crédito.')
        if self.related_invoice:
            if self.related_invoice.client != note.client:
                raise UserError('La factura relacionada debe pertenecer al cliente de la nota.')
            if self.related_invoice.company_id != note.company_id:
                raise UserError('La factura relacionada pertenece a otra compañía.')
            if self.related_invoice.is_draft:
                raise UserError('La factura relacionada debe estar confirmada.')
        if self.who_created and note.who_created and self.who_created != note.who_created:
            raise UserError('El creador del wizard no coincide con la nota de crédito.')

    def action_confirm_verification(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant', 'werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Caja o Gerencia para verificar notas de crédito.',
        )
        if not self.skip_related_invoice and not self.related_invoice:
            return display_warning_toast('Datos faltantes', 'Debe seleccionar una factura origen o indicar que se omite.')
        if not self.who_created or not self.who_approved:
            return display_warning_toast('Datos faltantes', 'Debe indicar quién creó y aprobó la nota.')
        if self.credit_note.state != 'draft':
            return display_warning_toast('Nota ya verificada', 'La nota de crédito ya fue verificada.')
        self._validate_verification_values()
        self.credit_note.sudo().write({
            'related_invoice': self.related_invoice.id if not self.skip_related_invoice else False,
            'who_created': self.who_created.id,
            'who_approved': self.env.user.id,
            'observations': self.observations,
            'state': 'verified',
        })
        return {'type': 'ir.actions.act_window_close'}
