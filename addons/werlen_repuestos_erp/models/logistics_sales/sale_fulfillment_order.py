from odoo import api, fields, models
from odoo.exceptions import UserError
from markupsafe import Markup
from datetime import datetime, time, timedelta
import pytz
from collections import defaultdict

from ...enums.logistics_sales.logistical_status import LOGISTICAL_STATUS_ENUM

from ...utils.group_verification import ensure_write_allowed_fields, ensure_user_in_groups

import logging

_logger = logging.getLogger(__name__)

class SaleFulfillmentOrder(models.Model):
    _name = 'sale_fulfillment_order'
    _description = 'Registro de: Orden De Venta'
    _rec_name = 'sale_fulfillment_order_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    """ Basic identifiers """
    sale_fulfillment_order_id = fields.Char(
        string='Orden De Venta',
        required=True,
        readonly=True,
        index=True
    )

    """ Sale fulfillment order INFO """

    time_of_preparation_start = fields.Datetime(
        string='Fecha y hora de inicio de preparación',
    )

    time_of_preparation_end = fields.Datetime(
        string='Fecha y hora de fin de preparación',
    )

    allow_deferred_payment = fields.Boolean(
        string='Permitir preparar sin pagar',
        help='La factura deberá quedar paga antes de ser entregada.',
        tracking=True,
    )

    allow_repayment = fields.Boolean(
        string='Contra-reembolso',
        help='Permite entregar el pedido para cobrarlo contra entrega.',
        tracking=True,
    )

    time_of_handing_over = fields.Datetime(
        string='Fecha y hora de entrega',
        index=True
    )

    observations = fields.Text(
        string='Observaciones',
        tracking=True
    )

    logistical_status = fields.Selection(
        LOGISTICAL_STATUS_ENUM,
        string='Estado logístico',
        default='draft',
        tracking=True,
        index=True,
    )

    is_account_move = fields.Boolean(
        string='Cuenta Corriente',
        related='invoice_id.is_account_move',
        store=True,
        readonly=True,
    )

    payment_status = fields.Selection(
        string='Estado de pago',
        related='invoice_id.payment_status',
        store=True,
        readonly=True,
    )

    amount_not_paid_unconfirmed = fields.Monetary(
        string='Importe pendiente',
        related='invoice_id.amount_not_paid_unconfirmed',
        store=True,
        readonly=True,
    )

    amount_paid_confirmed = fields.Monetary(
        string='Importe pagado confirmado',
        related='invoice_id.amount_paid_confirmed',
        store=True,
        readonly=True,
    )

    related_payment_lines = fields.Many2many(
        comodel_name='payment_line',
        compute='_compute_related_payment_lines',
        string='Pagos asociados',
    )

    who_withdraws = fields.Many2one(
        comodel_name='res.partner',
        string='Retira',
        tracking=True
    )

    who_prepared = fields.Many2one(
        comodel_name='res.users',
        string='Prepara',
    )

    who_handed_over = fields.Many2one(
        comodel_name='res.users',
        string='Entrega',
    )

    point_of_sale = fields.Many2one(
        comodel_name='point_of_sale',
        string='Punto de venta',
    )

    """ Other relationships """
    invoice_id = fields.Many2one(
        comodel_name='invoice_out',
        string='Factura',
        required=True,
        readonly=True
    )

    client = fields.Many2one(
        related='invoice_id.client',
        string='Cliente',
        store=True,
        readonly=True,
    )

    client_identifier = fields.Char(
        related='invoice_id.client_identifier',
        string='Num Cliente',
        store=True,
        readonly=True,
    )

    full_name = fields.Char(
        related='invoice_id.full_name',
        string='Nombre del Cliente',
        store=True,
        readonly=True,
        index=True
    )

    company_id = fields.Many2one(
        related='invoice_id.company_id',
        string='Company',
        store=True,
        readonly=True,
    )

    currency_id = fields.Many2one(
        related='invoice_id.currency_id',
        string="Moneda",
        store=True,
        readonly=True,
    )

    total_cost = fields.Monetary(
        related='invoice_id.total_cost',
        string='Importe',
        store=True,
        readonly=True,
        index=True
    )

    city = fields.Many2one(
        'city',
        string='Ciudad',
        tracking=True
    )

    zip_code = fields.Char(
        string='Zip',
    )

    state = fields.Many2one(
        'res.country.state',
        string='Provincia',
    )

    destination = fields.Char(
        string='Destino',
        tracking=True
    )

    cellphone = fields.Char(
        string='Telefono',
        tracking=True
    )

    seller = fields.Many2one(
        related='invoice_id.seller',
        string='Vendedor',
        store=True,
        readonly=True,
    )

    seller_user_id = fields.Many2one(
        'res.users',
        string='Usuario vendedor',
        compute='_compute_seller_user_id',
        store=True,
        readonly=True,
    )

    is_asigned_to_preparation_team = fields.Boolean(
        string='Preparar al fondo',
        default=False,
        tracking=True
    )

    has_delivery = fields.Boolean(
        string='Envío con flete',
        tracking=True
    )

    packages_count = fields.Char(
        string='Bultos',
        default="No Especificado"
    )

    date = fields.Datetime(
        related='invoice_id.date',
        string='Fecha',
        store=True,
        readonly=True,
    )

    """ Computed fields """

    @api.depends('seller')
    def _compute_seller_user_id(self):
        for rec in self:
            rec.seller_user_id = rec.seller

    @api.depends('invoice_id', 'invoice_id.reconciliation_lines')
    def _compute_related_payment_lines(self):
        payment_model = self.env['payment_line']
        for record in self:
            lines = record.invoice_id.reconciliation_lines if record.invoice_id else self.env['reconciliation_line']
            record.related_payment_lines = payment_model.search([
                ('reconciliation_lines_when_incomming', 'in', lines.ids),
            ]) if lines else False

    def _payment_allows_preparation(self):
        self.ensure_one()
        return (
            self.payment_status in ('paid', 'account')
            or self.allow_deferred_payment
            or self.allow_repayment
        )

    def _payment_allows_delivery(self):
        self.ensure_one()
        return self.payment_status in ('paid', 'account') or self.allow_repayment

    def _update_payment_workflow(self):
        for record in self:
            if record.logistical_status == 'awaiting_payment' and record._payment_allows_preparation():
                record.sudo().write({
                    'logistical_status': 'awaiting_preparation',
                })
            elif (
                record.logistical_status in ('awaiting_preparation', 'in_preparation', 'prepared')
                and not record._payment_allows_preparation()
            ):
                record.sudo().write({
                    'logistical_status': 'awaiting_payment',
                })

    """ Methods """

    def _log_action(self, message):
        self.ensure_one()

        user = self.env.user
        timestamp_utc = fields.Datetime.now()
        timestamp_local = fields.Datetime.context_timestamp(
            self,
            timestamp_utc
        )
        timestamp_str = timestamp_local.strftime('%Y-%m-%d %H:%M:%S')

        body = Markup(f"""
            <ul style="margin:0;padding-left:16px;">
                <li><b>Acción:</b> {message}</li>
                <li><b>Usuario:</b> {user.name}</li>
                <li><b>Fecha:</b> {timestamp_str}</li>
            </ul>
        """)

        self.message_post(
            body=body,
            subtype_xmlid='mail.mt_note',
            author_id=self.env.user.partner_id.id,
        )

    def create_new_payment(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_sales', 'werlen_repuestos_erp.group_accountant'],
            error_message='Necesitas permisos de Ventas o Caja para registrar pagos.',
        )
        wizard = self.env['wizard_manual_payment_invoice_out'].create({
            'reconciliation_invoice_id': self.invoice_id.id,
            'amount': max(self.invoice_id.amount_not_paid_unconfirmed, 0.0),
            'invoice_out_total_amount': self.invoice_id.total_cost,
            'invoice_out_amount_not_reconciliated': self.invoice_id.amount_not_paid_unconfirmed,
            'payment_method': self.invoice_id.payment_method.id,
            'journal': self.invoice_id.payment_method.get_default_journal(self.env.user).id,
            'payer': self.client.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_manual_payment_invoice_out',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def show_reconciliation_lines(self):
        self.ensure_one()
        return self.invoice_id.show_reconciliation_lines()

    def show_payment_lines(self):
        self.ensure_one()
        return self.invoice_id.show_payment_lines()

    def open_manual_reconciliation_line_form(self):
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_accountant', 'werlen_repuestos_erp.group_administration'],
            error_message='Necesitas permisos de Caja o Administración para reconciliar pagos.',
        )
        return self.invoice_id.open_manual_reconciliation_line_form()

    def action_skip_logistical_tracking(self):
        for record in self:

            ensure_user_in_groups(
                self.env.user,
                [
                'werlen_repuestos_erp.group_management',
                'werlen_repuestos_erp.group_administration',
                ],
                error_message="Necesitas permisos de Gerencia o Administración para omitir el flujo común de las facturas.",
            )

            if record.logistical_status == 'draft':
                raise UserError("La factura no ha sido verificada. No se puede omitir el flujo.")

            vals = {
                'logistical_status': 'avoid_tracking',
                'time_of_handing_over': datetime.now(),
            }

            record.sudo().write(vals)

            record.sudo()._log_action("Verificación omitida. Esta factura no seguirá el flujo normal.")

    def action_restart_logistical_flow(self):
        for record in self:
            ensure_user_in_groups(
                self.env.user,
                [
                'werlen_repuestos_erp.group_management',
                ],
                error_message="Necesitas permisos de Gerencia para reiniciar el flujo de una orden de venta.",
            )

            if record.logistical_status != 'avoid_tracking':
                raise UserError("Solo se puede reiniciar el flujo de ordenes que estén en estado 'Sin Seguimiento'.")

            vals = {
                'logistical_status': (
                    'awaiting_preparation'
                    if record._payment_allows_preparation()
                    else 'awaiting_payment'
                ),
                'time_of_preparation_start': False,
                'time_of_preparation_end': False,
                'time_of_handing_over': False,
                'who_prepared': False,
                'who_handed_over': False,
            }

            record.sudo().write(vals)

            record.sudo()._log_action("Flujo logístico reiniciado. La orden vuelve al flujo normal.")

    def start_verification(self):
        # ACCESS CHECK
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            [
            'werlen_repuestos_erp.group_sales',
            ],
            error_message="Necesitas permisos de Ventas para verificar Ordenes de Venta.",
        )

        # VALIDATION CHECK
        if self.logistical_status != 'draft':
            raise UserError("La orden ya fue verificada.")

        # ACTION START
        wizard_vals = {
            'invoice_id': self.invoice_id.id,
            'sale_fulfillment_order_id': self.id,
            'current_step': 'step_1',

            # Defaults útiles
            'destination': self.invoice_id.destination,
            'city': self.invoice_id.city.id,
            'state': self.invoice_id.state.id,
            'cellphone': self.client.phone,
        }

        if self.invoice_id.payment_method.is_account_payment_method:
            wizard_vals['is_account_move'] = True
        else:
            wizard_vals['payments'] = [(0, 0, {
                'payment_method': self.invoice_id.payment_method.id,
                'amount': self.total_cost,
                    'journal': self.invoice_id.payment_method.get_default_journal(self.env.user).id,
            })]

        wizard = self.env['wizard_fulfillment_order_verification'].create(wizard_vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard_fulfillment_order_verification',
            'res_id': wizard.id,
            'view_mode': 'form',
            'name': 'Verificación',
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_fulfillment_order_verification_step_1'
            ).id,
            'target': 'new',
        }

    def _start_preparation_one(self):
        # ACCESS CHECK
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            [
            'werlen_repuestos_erp.group_sales',
            'werlen_repuestos_erp.group_preparation',
            ],
            error_message="Necesitas permisos de Preparación/Ventas para preparar Ordenes de Venta.",
        )

        # VALIDATION CHECK
        if not self._payment_allows_preparation():
            raise UserError(
                'Para iniciar la preparación debe pagarse la factura y confirmarse sus pagos.'
            )
        if self.logistical_status not in ('awaiting_payment', 'awaiting_preparation'):
            raise UserError("La factura no puede empezar a ser preparada.")

        # ACTION START
        vals = {
            'logistical_status': 'in_preparation',
            'time_of_preparation_start': fields.Datetime.now(),
            'who_prepared': self.env.user
        }
        self.sudo().write(vals)

        self.sudo()._log_action("Inicio de Preparación.")

    def start_preparation(self):
        self.ensure_one()
        self._start_preparation_one()

    def action_start_preparation_multi(self):
        for record in self:
            record._start_preparation_one()

    def undo_start_preparation(self):
        # ACCESS CHECK
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            [
            'werlen_repuestos_erp.group_sales',
            'werlen_repuestos_erp.group_preparation',
            ],
            error_message="Necesitas permisos de Preparación/Ventas para deshacer la preparación de Ordenes de Venta.",
        )

        # VALIDATION CHECK
        if self.logistical_status != 'in_preparation':
            raise UserError("La preparación de la factura no fue iniciada y se intentó cancelarla")

        # ACTION START
        vals = {
            'logistical_status': 'awaiting_preparation',
            'time_of_preparation_start': False,
            'who_prepared': False
        }

        self.sudo().write(vals)

        self.sudo()._log_action("Deshacer Inicio de Preparación.")

    def _finish_preparation(self):
        # ACCESS CHECK
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            [
            'werlen_repuestos_erp.group_sales',
            'werlen_repuestos_erp.group_preparation',
            ],
            error_message="Necesitas permisos de Preparación/Ventas para finalizar la preparación de Ordenes de Venta.",
        )

        # VALIDATION CHECK
        if self.logistical_status != 'in_preparation':
            raise UserError("La factura no está en estado de preparación y se intentó finalizarla.")

        vals = {
            'logistical_status': 'prepared',
            'time_of_preparation_end': fields.Datetime.now(),
        }

        self.sudo().write(vals)

        self.sudo()._log_action("Fin de Preparación.")

    def finish_preparation(self):
        self.ensure_one()
        self._finish_preparation()

    def action_open_wizard_preparation(self):
        # ACCESS CHECK
        ensure_user_in_groups(
            self.env.user,
            [
            'werlen_repuestos_erp.group_sales',
            'werlen_repuestos_erp.group_preparation',
            ],
            error_message="Necesitas permisos de Preparación/Ventas para finalizar la preparación de Ordenes de Venta.",
        )

        # ACTION START
        return {
            'name': 'Preparación',
            'view_mode': 'form',
            'res_model': 'wizard_preparation',
            'view_id': self.env.ref('werlen_repuestos_erp.wizard_preparation_form_view').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {
                'default_saler_order_ids': self.ids
            }
        }

    def undo_finish_preparation(self):
        # ACCESS CHECK
        self.ensure_one()
        ensure_user_in_groups(
            self.env.user,
            [
            'werlen_repuestos_erp.group_sales',
            'werlen_repuestos_erp.group_preparation',
            ],
            error_message="Necesitas permisos de Preparación/Ventas para deshacer la preparación de Ordenes de Venta.",
        )

        # VALIDATION CHECK
        if self.logistical_status != 'prepared':
            raise UserError("No se puede deshacer la preparación de la factura")

        # ACTION START
        max_hours_allowed_for_undo_finish_preparation = float(
            self.env['ir.config_parameter'].sudo().get_param('werlen_repuestos_erp.max_hours_passed_to_allow_undo_preparation_status') or 0.1
        )
        max_seconds_allowed = max_hours_allowed_for_undo_finish_preparation*60*60

        if not self.env.user.has_group('werlen_repuestos_erp.group_administration'):
            if (fields.Datetime.now() - self.time_of_preparation_end).total_seconds() > max_seconds_allowed:
                raise UserError("Se ha excedido el tiempo permitido para deshacer la preparación de la factura. Ahora solo un administrador puede deshacerla.")

        vals = {
            'logistical_status': 'in_preparation',
            'time_of_preparation_end': False,
            'packages_count': 'No Especificado'
        }

        self.sudo().write(vals)

        self.sudo()._log_action("Deshacer Fin de Preparación.")

    def hand_out(self):
        # ACCESS CHECK
        ensure_user_in_groups(
            self.env.user,
            [
            'werlen_repuestos_erp.group_sales',
            'werlen_repuestos_erp.group_preparation',
            'werlen_repuestos_erp.group_accountant',
            ],
            error_message="Necesitas permisos de Preparación/Ventas/Caja para entregar Ordenes de Venta.",
        )

        # VALIDATION CHECK
        for rec in self:
            if rec.logistical_status != 'prepared':
                raise UserError("La factura no fue preparada y se intentó entregarla")
            if not rec._payment_allows_delivery():
                raise UserError("La factura no fue pagada y no se puede entregar.")

            # ACTION START
            vals = {
                'logistical_status': 'sent',
                'who_handed_over': self.env.user.id,
                'time_of_handing_over': fields.Datetime.now(),
            }

            rec.sudo().write(vals)

        for rec in self:
            rec.sudo()._log_action("Entrega de Mercadería.")

    def undo_hand_out(self):
        # ACCESS CHECK
        ensure_user_in_groups(
            self.env.user,
            [
            'werlen_repuestos_erp.group_sales',
            'werlen_repuestos_erp.group_preparation',
            'werlen_repuestos_erp.group_accountant',
            ],
            error_message="Necesitas permisos de Preparación/Ventas/Caja para deshacer la entrega de Ordenes de Venta.",
        )

        for rec in self:
            # VALIDATION CHECK
            if rec.logistical_status != 'sent':
                raise UserError("La factura no fue entregada y se intentó deshacer la entrega")

            max_hours_allowed_for_undo_hand_out = float(
                rec.env['ir.config_parameter'].sudo().get_param('werlen_repuestos_erp.max_hours_passed_to_allow_undo_hand_out') or 0.1
            )
            max_seconds_allowed = max_hours_allowed_for_undo_hand_out*60*60

            if not rec.env.user.has_group('werlen_repuestos_erp.group_administration'):
                if (fields.Datetime.now() - rec.time_of_handing_over).total_seconds() > max_seconds_allowed:
                    raise UserError("Se ha excedido el tiempo permitido para deshacer la entrega de la factura. Ahora solo un administrador puede deshacerla.")

            # ACTION START
            vals = {
                'logistical_status': 'prepared',
                'who_handed_over': False,
                'time_of_handing_over': False
            }

            rec.sudo().write(vals)

        for rec in self:
            rec.sudo()._log_action("Deshacer Entrega de Mercadería.")

    """ Methods for dashboard """

    @classmethod
    def _get_today_handing_over_domain(cls, user):
        tz = pytz.timezone(user.tz or "UTC")
        today = fields.Date.context_today(user)

        start_local = tz.localize(datetime.combine(today, time.min))
        end_local = tz.localize(datetime.combine(today, time.max))

        return [
            ("time_of_handing_over", ">=", start_local.astimezone(pytz.utc)),
            ("time_of_handing_over", "<=", end_local.astimezone(pytz.utc)),
        ]

    @api.model
    def get_seller_dashboard_data(self):
        self = self.sudo()
        user = self.env.user

        logistics = [
            ("draft", "Borrador"),
            ("awaiting_payment", "A pagar"),
            ("awaiting_preparation", "A preparar"),
            ("in_preparation", "En preparación"),
            ("prepared", "Preparado"),
            ("sent", "Entregado (hoy)"),
        ]

        payment_states = [
            ("paid", "Pagado", "paid"),
            ("partially_paid", "Parcial", "partial"),
            ("not_paid", "No pagado", "unpaid"),
            ("account", "Cuenta-Corriente", "account"),
        ]

        # -------------------------
        # 1) read_group principal
        # -------------------------

        grouped = self.read_group(
            domain=[
                ("seller_user_id", "=", user.id),
            ],
            fields=["logistical_status", "payment_status"],
            groupby=["logistical_status", "payment_status"],
            lazy=False
        )

        counter = defaultdict(int)

        for g in grouped:
            log = g["logistical_status"]
            pay = g["payment_status"]
            count = g["__count"]

            if log == "avoid_tracking":
                log = "sent"

            # Excluir sent + paid (se recalcula abajo)
            if log == "sent" and pay in ["paid", "account"]:
                continue

            counter[(log, pay)] += count

        # -------------------------
        # 2) Caso especial: sent + paid|account (solo hoy), and avoid tracking
        # -------------------------
        today_domain = self._get_today_handing_over_domain(user)

        sent_paid_today = self.search_count([
            ("seller_user_id", "=", user.id),
            ("logistical_status", "in", ["sent", "avoid_tracking"]),
            ("payment_status", "=", "paid"),
            ("time_of_handing_over", "!=", False),
        ] + today_domain)

        counter[("sent", "paid")] = sent_paid_today

        sent_account_today = self.search_count([
            ("seller_user_id", "=", user.id),
            ("logistical_status", "in", ["sent", "avoid_tracking"]),
            ("payment_status", "=", "account"),
            ("time_of_handing_over", "!=", False),
        ] + today_domain)

        counter[("sent", "account")] = sent_account_today

        # -------------------------
        # 3) Construcción del resultado
        # -------------------------
        columns = []

        for log_key, log_label in logistics:
            segments = []
            total = 0

            for pay_key, pay_label, pay_css in payment_states:
                count = counter[(log_key, pay_key)]
                total += count

                segments.append({
                    "key": pay_key,
                    "label": pay_label,
                    "count": count,
                    "css": f"segment-{pay_css}",
                })

            columns.append({
                "key": log_key,
                "label": log_label,
                "total": total,
                "segments": segments,
            })

        return {
            "columns": columns,
        }


    @api.model
    def get_accountant_dashboard_data(self):
        self = self.sudo()
        user = self.env.user

        """ Credit_note_out Data """
        unreconciliated_cn_count = self.env["credit_note_out"].search_count([
            ("payment_status", "in", ["not_paid", "partially_paid"])
        ])

        """ Invoice_out Data """
        logistics = [
            ("draft", "Borrador"),
            ("awaiting_payment", "A pagar"),
            ("awaiting_preparation", "A preparar"),
            ("in_preparation", "En preparación"),
            ("prepared", "Preparado"),
            ("sent", "Entregado (hoy)"),
        ]

        payment_states = [
            ("paid", "Pagado", "paid"),
            ("partially_paid", "Parcial", "partial"),
            ("not_paid", "No pagado", "unpaid"),
            ("account", "Cuenta-Corriente", "account"),
        ]

        # -------------------------
        # 1) read_group principal (GLOBAL)
        # -------------------------

        grouped = self.read_group(
            domain=[],
            fields=["logistical_status", "payment_status"],
            groupby=["logistical_status", "payment_status"],
            lazy=False,
        )

        counter = defaultdict(int)

        for g in grouped:
            log = g["logistical_status"]
            pay = g["payment_status"]
            count = g["__count"]

            if log == "avoid_tracking":
                log = "sent"

            # Excluir sent + paid (se recalcula abajo)
            if log == "sent" and pay in ["paid", "account"]:
                continue

            counter[(log, pay)] += count

        # -------------------------
        # 2) Caso especial: sent + paid|account (solo hoy), and avoid tracking
        # -------------------------

        today_domain = self._get_today_handing_over_domain(user)

        sent_paid_today = self.search_count([
            ("logistical_status", "in", ["sent", "avoid_tracking"]),
            ("payment_status", "=", "paid"),
            ("time_of_handing_over", "!=", False),
        ] + today_domain)

        counter[("sent", "paid")] = sent_paid_today

        sent_account_today = self.search_count([
            ("logistical_status", "in", ["sent", "avoid_tracking"]),
            ("payment_status", "=", "account"),
            ("time_of_handing_over", "!=", False),
        ] + today_domain)

        counter[("sent", "account")] = sent_account_today

        # -------------------------
        # 3) Construcción del resultado
        # -------------------------

        columns = []

        for log_key, log_label in logistics:
            segments = []
            total = 0

            for pay_key, pay_label, pay_css in payment_states:
                count = counter[(log_key, pay_key)]
                total += count

                segments.append({
                    "key": pay_key,
                    "label": pay_label,
                    "count": count,
                    "css": f"segment-{pay_css}",
                })

            columns.append({
                "key": log_key,
                "label": log_label,
                "total": total,
                "segments": segments,
            })

        return {
            "columns": columns,
            "unreconciled_credit_notes_count": unreconciliated_cn_count,
        }

    @api.model
    def get_preparation_team_dashboard_data(self):
        user = self.env.user
        MAX_BOXES = 12

        logistics = [
            ("awaiting_preparation", "A preparar"),
            ("in_preparation", "En preparación"),
            ("prepared", "Preparado"),
            ("sent", "Entregado hoy"),
        ]

        # -------------------------
        # 1) Conteo por read_group
        # -------------------------
        base_domain = [
            ("is_asigned_to_preparation_team", "=", True),
            ("logistical_status", "in", [
                "awaiting_preparation",
                "in_preparation",
                "prepared",
            ]),
        ]

        grouped = self.read_group(
            domain=base_domain,
            fields=["logistical_status"],
            groupby=["logistical_status"],
        )

        counter = {key: 0 for key, _ in logistics}

        for g in grouped:
            status = g["logistical_status"]
            counter[status] = g["logistical_status_count"]

        # -------------------------
        # 2) Conteo especial: sent (solo hoy)
        # -------------------------
        today_domain = self._get_today_handing_over_domain(user)

        sent_count = self.search_count([
            ("is_asigned_to_preparation_team", "=", True),
            ("logistical_status", "=", "sent"),
            ("time_of_handing_over", "!=", False),
        ] + today_domain)

        counter["sent"] = sent_count

        # -------------------------
        # 3) Formato final
        # -------------------------
        columns = []
        for key, label in logistics:
            columns.append({
                "key": key,
                "label": label,
                "count": counter[key],
            })

        return {
            "columns": columns,
            "max_boxes": MAX_BOXES,
        }

    @api.model
    def get_admin_dashboard_data(self):
        self = self.sudo()

        limit_time = fields.Datetime.now() - timedelta(minutes=30)

        # =========================================================
        # 1) VENTAS (sale_fulfillment_order)
        # =========================================================

        invoice_model = self.env["sale_fulfillment_order"]

        draft_old = invoice_model.search_count([
            ("logistical_status", "=", "draft"),
            ("create_date", "<", limit_time),
        ])
        draft_old_risk_level = "normal"
        if draft_old > 0:
            draft_old_risk_level = "warning"
        if draft_old > 5:
            draft_old_risk_level = "critical"

        not_reconciled_invoices = invoice_model.search_count([
            ("payment_status", "in", ["not_paid", "partially_paid"]),
            ("create_date", "<", limit_time),
        ])
        not_reconciled_invoices_risk_level = "normal"
        if not_reconciled_invoices > 24:
            not_reconciled_invoices_risk_level = "warning"
        if not_reconciled_invoices > 35:
            not_reconciled_invoices_risk_level = "critical"

        not_associated_with_credit_note = invoice_model.search_count([
            ('payment_status', 'in', ['not_paid', 'partially_paid'])
        ])
        not_associated_with_credit_note_risk_level = "normal"
        if not_associated_with_credit_note > 0:
            not_associated_with_credit_note_risk_level = "warning"
        if not_associated_with_credit_note > 5:
            not_associated_with_credit_note_risk_level = "critical"

        sales_model = {
            "key": "sale_fulfillment_order",
            "label": "Ventas",
            "issues": [
                {
                    "key": "draft_old",
                    "label": "En Borrador > 30 min",
                    "count": draft_old,
                    "risk_level": draft_old_risk_level,
                    "action": "werlen_repuestos_erp.action_open_seller_sale_fulfillment_order",
                },
                {
                    "key": "not_reconciled",
                    "label": "No reconciliadas > 30 min",
                    "count": not_reconciled_invoices,
                    "risk_level": not_reconciled_invoices_risk_level,
                    "action": "werlen_repuestos_erp.action_open_relevant_accountant_sale_fulfillment_order_list_view",
                },
                {
                    "key": "not_associated_with_credit_note",
                    "label": "Sin Nota de Crédito asociada",
                    "count": not_associated_with_credit_note,
                    "risk_level": not_associated_with_credit_note_risk_level,
                    "action": "werlen_repuestos_erp.action_open_seller_sale_fulfillment_order",
                },
            ]
        }

        # =========================================================
        # 2) NOTAS DE CRÉDITO (credit_note_out)
        # =========================================================

        credit_model = self.env["credit_note_out"]

        credit_notes_not_verified = credit_model.search_count([
            ("state", "=", "draft"),
        ])
        credit_notes_not_verified_risk_level = "normal"
        if credit_notes_not_verified > 0:
            credit_notes_not_verified_risk_level = "warning"
        if credit_notes_not_verified > 5:
            credit_notes_not_verified_risk_level = "critical"

        credit_notes_not_reconciled = credit_model.search_count([
            ("payment_status", "in", ["not_paid", "partially_paid"]),
        ])
        credit_notes_not_reconciled_risk_level = "normal"
        if credit_notes_not_reconciled > 9:
            credit_notes_not_reconciled_risk_level = "warning"
        if credit_notes_not_reconciled > 15:
            credit_notes_not_reconciled_risk_level = "critical"

        credit_notes_model = {
            "key": "credit_note_out",
            "label": "Notas de Crédito",
            "issues": [
                {
                    "key": "not_verified",
                    "label": "No verificadas",
                    "count": credit_notes_not_verified,
                    "risk_level": credit_notes_not_verified_risk_level,
                    "action": "werlen_repuestos_erp.action_open_credit_notes_out",
                },
                {
                    "key": "not_reconciled",
                    "label": "No reconciliadas",
                    "count": credit_notes_not_reconciled,
                    "risk_level": credit_notes_not_reconciled_risk_level,
                    "action": "werlen_repuestos_erp.action_open_credit_notes_out",
                },
            ]
        }

        # =========================================================
        # 3) RECLAMOS DE CLIENTE (client_claim)
        # =========================================================

        client_claim_model = self.env["client_claim"]

        client_claims_in_draft = client_claim_model.search_count([
            ("state", "=", "draft"),
        ])
        client_claims_in_draft_risk_level = "normal"
        if client_claims_in_draft > 0:
            client_claims_in_draft_risk_level = "warning"
        if client_claims_in_draft > 5:
            client_claims_in_draft_risk_level = "critical"

        client_claims_unresolved = client_claim_model.search_count([
            ("state", "=", "valid"),
        ])
        client_claims_unresolved_risk_level = "normal"
        if client_claims_unresolved > 19:
            client_claims_unresolved_risk_level = "warning"
        if client_claims_unresolved > 35:
            client_claims_unresolved_risk_level = "critical"

        client_claims_without_supplier_claim = client_claim_model.search_count([
            ("supplier_claim_pending", "=", True),
        ])
        client_claims_without_supplier_claim_risk_level = "normal"
        if client_claims_without_supplier_claim > 0:
            client_claims_without_supplier_claim_risk_level = "warning"
        if client_claims_without_supplier_claim > 5:
            client_claims_without_supplier_claim_risk_level = "critical"

        client_claims_model = {
            "key": "client_claim",
            "label": "Reclamos de Clientes",
            "issues": [
                {
                    "key": "draft",
                    "label": "En borrador",
                    "count": client_claims_in_draft,
                    "risk_level": client_claims_in_draft_risk_level,
                    "action": "werlen_repuestos_erp.action_open_client_claims",
                },
                {
                    "key": "unresolved",
                    "label": "No resueltos",
                    "count": client_claims_unresolved,
                    "risk_level": client_claims_unresolved_risk_level,
                    "action": "werlen_repuestos_erp.action_open_client_claims",
                },
                {
                    "key": "without_supplier_claim",
                    "label": "Sin reclamar al proveedor",
                    "count": client_claims_without_supplier_claim,
                    "risk_level": client_claims_without_supplier_claim_risk_level,
                    "action": "werlen_repuestos_erp.action_open_client_claims",
                },
            ]
        }

        # =========================================================
        # 4) RECLAMOS A PROVEEDORES (supplier_claim + return_note)
        # =========================================================

        supplier_claim_model = self.env["supplier_claim"]
        open_supplier_claims = supplier_claim_model.search_count([
            ("state", "=", "open"),
        ])
        open_supplier_claims_risk_level = "normal"
        if open_supplier_claims > 9:
            open_supplier_claims_risk_level = "warning"
        if open_supplier_claims > 20:
            open_supplier_claims_risk_level = "critical"

        supplier_claims_in_progress = supplier_claim_model.search_count([
            ("state", "=", "in_progress"),
        ])
        supplier_claims_in_progress_risk_level = "normal"
        if supplier_claims_in_progress > 149:
            supplier_claims_in_progress_risk_level = "warning"
        if supplier_claims_in_progress > 250:
            supplier_claims_in_progress_risk_level = "critical"

        return_note_model = self.env["return_note"]
        unsent_return_notes = return_note_model.search_count([
            ("state", "in", ["draft", "prepared"]),
        ])
        unsent_return_notes_risk_level = "normal"
        if unsent_return_notes > 2:
            unsent_return_notes_risk_level = "warning"
        if unsent_return_notes > 6:
            unsent_return_notes_risk_level = "critical"

        supplier_claims_model = {
            "key": "supplier_claim",
            "label": "Reclamos a Proveedores",
            "issues": [
                {
                    "key": "open",
                    "label": "Reclamos abiertos",
                    "count": open_supplier_claims,
                    "risk_level": open_supplier_claims_risk_level,
                    "action": "werlen_repuestos_erp.action_open_supplier_claims",
                },
                {
                    "key": "in_progress",
                    "label": "Reclamos en gestión",
                    "count": supplier_claims_in_progress,
                    "risk_level": supplier_claims_in_progress_risk_level,
                    "action": "werlen_repuestos_erp.action_open_supplier_claims",
                },
                {
                    "key": "unsent_returns",
                    "label": "Devoluciones no enviadas",
                    "count": unsent_return_notes,
                    "risk_level": unsent_return_notes_risk_level,
                    "action": "werlen_repuestos_erp.action_open_return_notes",
                },
            ]
        }

        # =========================================================
        # 5) RECIBOS (account_payment)
        # =========================================================

        payment_model = self.env["account_payment"]

        payments_not_verified = payment_model.search_count([
            ("status", "=", "draft"),
        ])
        payments_not_verified_risk_level = "normal"
        if payments_not_verified > 0:
            payments_not_verified_risk_level = "warning"
        if payments_not_verified > 3:
            payments_not_verified_risk_level = "critical"

        payments_not_reconciled = payment_model.search_count([
            ("payment_status", "in", ["not_paid", "partially_paid"]),
        ])
        payments_not_reconciled_risk_level = "normal"
        if payments_not_reconciled > 0:
            payments_not_reconciled_risk_level = "warning"
        if payments_not_reconciled > 3:
            payments_not_reconciled_risk_level = "critical"

        receipts_model = {
            "key": "account_payment",
            "label": "Recibos",
            "issues": [
                {
                    "key": "not_verified",
                    "label": "No verificados",
                    "count": payments_not_verified,
                    "risk_level": payments_not_verified_risk_level,
                    "action": "werlen_repuestos_erp.action_open_account_payments",
                },
                {
                    "key": "not_reconciled",
                    "label": "Sin movimientos asociados",
                    "count": payments_not_reconciled,
                    "risk_level": payments_not_reconciled_risk_level,
                    "action": "werlen_repuestos_erp.action_open_account_payments",
                },
            ]
        }

        # =========================================================
        # 6) MOVIMIENTOS (payment_line + check)
        # =========================================================

        payment_line_model = self.env["payment_line"]
        check_model = self.env["check"]

        # Agrupar payment_line
        grouped_payment_lines = payment_line_model.read_group(
            domain=[("payment_status", "in", ["not_paid", "partially_paid"])],
            fields=["payment_origin_explanation"],
            groupby=["payment_origin_explanation"],
            lazy=False,
        )

        # Agrupar checks
        grouped_checks = check_model.read_group(
            domain=[("payment_status", "in", ["not_paid", "partially_paid"])],
            fields=["payment_origin_explanation"],
            groupby=["payment_origin_explanation"],
            lazy=False,
        )

        explanation_labels = {
            "account_in": "Ingreso a Cuenta Corriente",
            "down_payment": "Seña",
            "payment_for_invoice_out": "Pago de Factura",
            "payment_for_credit_note_out": "Pago por Nota de Crédito",
        }

        counter = defaultdict(int)

        # Sumar payment_lines
        for g in grouped_payment_lines:
            key = g["payment_origin_explanation"]
            counter[key] += g["__count"]

        # Sumar checks
        for g in grouped_checks:
            key = g["payment_origin_explanation"]
            counter[key] += g["__count"]

        movement_issues = []

        for key, label in explanation_labels.items():
            movement_issues.append({
                "key": f"reason_{key}",
                "label": label,
                "count": counter[key],
                "risk_level": "normal",
            })

            # Set action for each origin reason
            if key == "account_in":
                movement_issues[-1]["action"] = f"werlen_repuestos_erp.action_open_payment_lines"
            if key == "down_payment":
                movement_issues[-1]["action"] = f"werlen_repuestos_erp.action_open_payment_lines"
            elif key == "payment_for_invoice_out":
                movement_issues[-1]["action"] = f"werlen_repuestos_erp.action_open_payment_lines"
            elif key == "payment_for_credit_note_out":
                movement_issues[-1]["action"] = f"werlen_repuestos_erp.action_open_payment_lines"


        for move in movement_issues:
            if move["count"] > 3:
                move["risk_level"] = "warning"
            if move["count"] > 6:
                move["risk_level"] = "critical"


        movements_model = {
            "key": "movements",
            "label": "Movimientos No Asociados",
            "issues": movement_issues,
        }

        # =========================================================
        # RESULTADO FINAL
        # =========================================================

        models = [
            sales_model,
            credit_notes_model,
            client_claims_model,
            supplier_claims_model,
            receipts_model,
            movements_model,
        ]

        return {
            "models": models
        }


    """ Overrides """

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            ensure_user_in_groups(
                self.env.user,
                [
                    'werlen_repuestos_erp.group_sales',
                    'werlen_repuestos_erp.group_administration',
                    'werlen_repuestos_erp.group_system',
                ],
                error_message='Necesitas permisos para crear Ordenes de Venta.',
            )
        for values in vals_list:
            if values.get('logistical_status', 'draft') != 'draft' and not self.env.su:
                raise UserError(
                    'Las órdenes nuevas deben comenzar en estado de borrador.'
                )
            invoice = self.env['invoice_out'].browse(values.get('invoice_id')).exists()
            if not invoice:
                raise UserError('La orden debe estar asociada a una factura válida.')
        return super().create(vals_list)

    def _check_write_permissions_one(self, vals):
        user = self.env.user

        ensure_user_in_groups(
            user,
            [
            'werlen_repuestos_erp.group_sales',
            'werlen_repuestos_erp.group_administration',
            'werlen_repuestos_erp.group_system',
            'werlen_repuestos_erp.group_accountant',
            ],
            error_message="Necesitas permisos de Ventas/Administración/Caja para modificar Ordenes de Venta."
        )

        if self.logistical_status == 'draft':
            EDITABLE_FIELDS_BY_GROUP = {
                'werlen_repuestos_erp.group_system': {
                    '*'
                },
            }

            ensure_write_allowed_fields(self, user, vals, EDITABLE_FIELDS_BY_GROUP)

        elif self.logistical_status in [
            'awaiting_payment',
            'awaiting_preparation',
            'in_preparation',
            'prepared',
            'avoid_tracking',
            ]:
            EDITABLE_FIELDS_BY_GROUP = {
                'werlen_repuestos_erp.group_sales': {
                    'observations',
                    'destination',
                    'city',
                    'state',
                    'cellphone',
                    'is_asigned_to_preparation_team',
                    'has_delivery',
                    'who_withdraws',
                    'point_of_sale'
                },
                'werlen_repuestos_erp.group_administration': {
                    'observations',
                    'destination',
                    'city',
                    'state',
                    'cellphone',
                    'is_asigned_to_preparation_team',
                    'has_delivery',
                    'who_withdraws',
                    'point_of_sale'
                },
                'werlen_repuestos_erp.group_accountant': {
                    'observations',
                },
                'werlen_repuestos_erp.group_system': {
                    '*'
                },
            }

            ensure_write_allowed_fields(self, user, vals, EDITABLE_FIELDS_BY_GROUP)

        elif self.logistical_status == 'sent':
            EDITABLE_FIELDS_BY_GROUP = {
                'werlen_repuestos_erp.group_sales': {
                    'observations',
                },
                'werlen_repuestos_erp.group_administration': {
                    'observations',
                },
                'werlen_repuestos_erp.group_accountant': {
                    'observations',
                },
                'werlen_repuestos_erp.group_system': {
                    '*'
                },
            }

            ensure_write_allowed_fields(self, user, vals, EDITABLE_FIELDS_BY_GROUP)

    def _check_write_permissions(self, vals):
        for rec in self:
            rec._check_write_permissions_one(vals)

    def write(self, vals):
        self._check_write_permissions(vals)
        return super().write(vals)

    """ SQL Constraints """

    _sql_constraints = [

        # Identificador único de la orden
        (
            'sale_fulfillment_order_id_uniq',
            'unique(sale_fulfillment_order_id)',
            'Ya existe una orden de venta con este identificador.'
        ),

        # Required: sale_fulfillment_order_id
        (
            'sale_fulfillment_order_id_not_null',
            'CHECK(sale_fulfillment_order_id IS NOT NULL)',
            'El identificador de la orden es obligatorio.'
        ),

        # Required: invoice_id
        (
            'sale_fulfillment_order_invoice_not_null',
            'CHECK(invoice_id IS NOT NULL)',
            'La orden debe estar asociada a una factura.'
        ),

    ]
