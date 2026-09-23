from odoo import api, fields, models
from odoo.exceptions import UserError

from ....utils.group_verification import ensure_user_in_groups


class SupplierPayment(models.Model):
    _name = 'supplier_payment'
    _description = 'Pago a proveedor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'name desc'

    name = fields.Char(
        string='Identificador', required=True, readonly=True, index=True,
        copy=False, default='Nuevo',
    )
    state = fields.Selection(
        selection=[('pending', 'Pendiente'), ('used', 'Usado')],
        string='Estado', default='pending', required=True, index=True,
        tracking=True,
    )
    supplier_id = fields.Many2one(
        comodel_name='supplier.payment.supplier', string='Proveedor',
        required=True, index=True, tracking=True,
    )
    payment_method_id = fields.Many2one(
        comodel_name='supplier_payment_method', string='Método/Origen del pago',
        required=True, tracking=True,
    )
    payment_destination_id = fields.Many2one(
        comodel_name='supplier_payment_destination', string='Destino de pago',
        required=True, tracking=True,
    )
    payment_method_amount = fields.Monetary(
        string='Monto en método de pago', required=True, tracking=True,
        help='Importe correspondiente solo al método de pago, excluyendo cheques.',
    )
    check_ids = fields.Many2many(
        comodel_name='check', string='Cheques utilizados', tracking=True,
    )
    check_total_amount = fields.Monetary(
        string='Monto en cheques', compute='_compute_check_total_amount',
        store=True, currency_field='currency_id',
    )
    total_amount = fields.Monetary(
        string='Importe total', compute='_compute_total_amount', store=True,
        currency_field='currency_id', tracking=True,
    )
    payment_date = fields.Date(
        string='Fecha de pago', required=True, index=True, tracking=True,
        default=fields.Date.context_today,
    )
    use_date = fields.Date(string='Fecha de uso', tracking=True)
    related_payment_orders = fields.Text(
        string='Órdenes de pago relacionadas', tracking=True,
    )
    observations = fields.Text(string='Observaciones', tracking=True)
    who_created = fields.Many2one(
        comodel_name='res.users', string='Registrado por',
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        comodel_name='res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency', string='Moneda',
        related='company_id.currency_id', store=True,
    )

    @api.depends('check_ids', 'check_ids.amount')
    def _compute_check_total_amount(self):
        for record in self:
            record.check_total_amount = sum(record.check_ids.mapped('amount'))

    @api.depends('payment_method_amount', 'check_total_amount')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = record.payment_method_amount + record.check_total_amount

    @api.constrains('payment_method_amount')
    def _check_payment_method_amount(self):
        for record in self:
            if record.payment_method_amount < 0:
                raise UserError('El monto del método de pago no puede ser negativo.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('supplier.payment') or 'Nuevo'
        return super().create(vals_list)

    def action_open_confirm_use_wizard(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user, ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para confirmar el uso de un pago a proveedor.',
        )
        return {
            'type': 'ir.actions.act_window', 'name': 'Confirmar uso del pago',
            'res_model': 'wizard_confirm_supplier_payment_use', 'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_supplier_payment_id': self.id,
                'default_use_date': self.use_date,
                'default_related_payment_orders': self.related_payment_orders,
                'default_observations': self.observations,
            },
        }

    def action_undo_use(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user, ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para deshacer el uso de un pago a proveedor.',
        )
        self.write({'state': 'pending', 'use_date': False})

    def action_open_add_checks_wizard(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user, ['werlen_repuestos_erp.group_management'],
            error_message='Necesitas permisos de Gerencia para asociar cheques.',
        )
        return {
            'type': 'ir.actions.act_window', 'name': 'Asociar cheques',
            'res_model': 'wizard_add_checks_to_supplier_payment',
            'view_mode': 'form', 'target': 'new',
            'context': {'default_supplier_payment_id': self.id},
        }

    _sql_constraints = [
        (
            'payment_method_amount_positive',
            'CHECK(payment_method_amount >= 0)',
            'El monto del método de pago no puede ser negativo.',
        ),
    ]
