from odoo import models, fields, api
from odoo.exceptions import UserError
from markupsafe import Markup
from datetime import datetime, time
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

    allow_deferred_payment = fields.Boolean(
        string='Permitir preparar sin pagar',
        help="Permite empezar a preparar el pedido sin haber pagado la factura. Sigue siendo necesario pagar antes de entregar el pedido.",
        tracking=True
    )

    is_account_move = fields.Boolean(
        string='Cuenta Corriente',
        related='invoice_id.is_account_move',
        readonly=True,
        store=True
    )

    allow_repayment = fields.Boolean(
        string='Contra-Reembolso',
        help="Normalmente usado cuando hay envio con fletero y el pago se realiza por contrareembolso.\nPermite entregar el pedido sin haber pagado la factura.",
        tracking=True
    )

    repayment_group = fields.Selection(
        [
            ('with_repayment', 'Contra-Reembolso'),
            ('without_repayment', 'Pago Normal'),
        ],
        string='Contra-Reembolso',
        compute='_compute_repayment_group',
        readonly=True,
        store=True
    )

    time_of_preparation_start = fields.Datetime(
        string='Fecha y hora de inicio de preparación',
    )

    time_of_preparation_end = fields.Datetime(
        string='Fecha y hora de fin de preparación',
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
        compute='_compute_logistical_status',
        store=True,
        tracking=True,
        index=True,
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

    payment_status = fields.Selection(
        related='invoice_id.payment_status',
        string='Pago',
        store=True,
        readonly=True,
    )

    has_missing_payment = fields.Boolean(
        compute="_compute_has_missing_payment",
        store=False
    )

    """ Computed fields """

    @api.depends('seller')
    def _compute_seller_user_id(self):
        for rec in self:
            rec.seller_user_id = rec.seller.user_ids[:1] if rec.seller else False

    @api.depends('invoice_id.payment_status', 'allow_deferred_payment', 'allow_repayment', 'is_account_move')
    def _compute_logistical_status(self):
        """
        Moves automatically between awaiting_payment and awaiting_preparation based on the payment status.
        """
        for rec in self:
            if ((rec.payment_status == 'paid') or rec.allow_deferred_payment or rec.allow_repayment or rec.is_account_move) and (rec.logistical_status == 'awaiting_payment'):
                rec.logistical_status = 'awaiting_preparation'
                rec._compute_logistical_status()

            if (rec.payment_status != 'paid' and not rec.allow_deferred_payment and not rec.allow_repayment and not rec.is_account_move) and (rec.logistical_status == 'awaiting_preparation'):
                rec.logistical_status = 'awaiting_payment'
                rec._compute_logistical_status()

    @api.depends('invoice_id.payment_status')
    def _compute_has_missing_payment(self):
        for rec in self:
            rec.has_missing_payment = rec.payment_status not in ['paid', 'account']

    @api.depends('allow_repayment')
    def _compute_repayment_group(self):
        for rec in self:
            rec.repayment_group = (
                'with_repayment' if rec.allow_repayment else 'without_repayment'
            )

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

    def log_action(self, message):
        self.ensure_one()
        if self.env.context.get('workflow_transition'):
            self._log_action(message)

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

            record.sudo().with_context(workflow_transition=True).write(vals)

            record.with_context(workflow_transition=True).log_action("Verificación omitida. Esta factura no seguirá el flujo normal.")

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
                'logistical_status': 'awaiting_payment',
                'time_of_preparation_start': False,
                'time_of_preparation_end': False,
                'time_of_handing_over': False,
                'who_prepared': False,
                'who_handed_over': False,
            }

            record.with_context(workflow_transition=True).write(vals)
            record.sudo()._compute_logistical_status()

            record.with_context(workflow_transition=True).log_action("Flujo logístico reiniciado. La orden vuelve al flujo normal.")

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
        if self.logistical_status == 'awaiting_payment':
            if (self.allow_deferred_payment or self.allow_repayment or self.is_account_move) == False:
                raise UserError("Para poder iniciar la preparación, se debe pagar la totalidad de la factura y confirmar los pagos asociados")
        elif self.logistical_status != 'awaiting_preparation':
            raise UserError("La factura no puede empezar a ser preparada.")

        # ACTION START
        vals = {
            'logistical_status': 'in_preparation',
            'time_of_preparation_start': fields.Datetime.now(),
            'who_prepared': self.env.user
        }
        self.sudo().with_context(workflow_transition=True).write(vals)

        self._log_action("Inicio de Preparación.")

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

        self.sudo().with_context(workflow_transition=True).write(vals)

        self._log_action("Deshacer Inicio de Preparación.")

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

        self.sudo().with_context(workflow_transition=True).write(vals)

        self._log_action("Fin de Preparación.")

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

        self.sudo().with_context(workflow_transition=True).write(vals)

        self._log_action("Deshacer Fin de Preparación.")

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
            if rec.payment_status != 'paid' and not rec.allow_repayment and not rec.is_account_move:
                raise UserError("La factura no fue pagada y se intentó entregarla")

            # ACTION START
            vals = {
                'logistical_status': 'sent',
                'who_handed_over': self.env.user.id,
                'time_of_handing_over': fields.Datetime.now(),
            }

            rec.sudo().with_context(workflow_transition=True).write(vals)

        for rec in self:
            rec.sudo().with_context(workflow_transition=True).log_action("Entrega de Mercadería.")

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

            rec.sudo().with_context(workflow_transition=True).write(vals)

        for rec in self:
            rec.sudo().with_context(workflow_transition=True).log_action("Deshacer Entrega de Mercadería.")

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

        base_domain = [
            ("seller_user_id", "=", user.id),
        ]

        grouped = self.read_group(
            domain=base_domain,
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

            if log == "sent" and pay in ["paid", "account"]:
                continue

            counter[(log, pay)] += count

        today_domain = self._get_today_handing_over_domain(user)

        sent_paid_today = self.search_count(
            base_domain
            + [
                ("logistical_status", "in", ["sent", "avoid_tracking"]),
                ("payment_status", "=", "paid"),
                ("time_of_handing_over", "!=", False),
            ]
            + today_domain
        )

        counter[("sent", "paid")] = sent_paid_today

        sent_account_today = self.search_count(
            base_domain
            + [
                ("logistical_status", "in", ["sent", "avoid_tracking"]),
                ("payment_status", "=", "account"),
                ("time_of_handing_over", "!=", False),
            ]
            + today_domain
        )

        counter[("sent", "account")] = sent_account_today

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
    def get_preparation_team_dashboard_data(self):
        user = self.env.user
        MAX_BOXES = 12

        logistics = [
            ("awaiting_preparation", "A preparar"),
            ("in_preparation", "En preparación"),
            ("prepared", "Preparado"),
            ("sent", "Entregado hoy"),
        ]

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

        today_domain = self._get_today_handing_over_domain(user)

        sent_count = self.search_count([
            ("is_asigned_to_preparation_team", "=", True),
            ("logistical_status", "=", "sent"),
            ("time_of_handing_over", "!=", False),
        ] + today_domain)

        counter["sent"] = sent_count

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

    """ Overrides """

    def _check_write_permissions_one(self, vals):
        # Only triggered when context workflow_transition == False. Which corresponds to a manual write, usually not using any wizard.

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
                    'allow_repayment',
                    'allow_deferred_payment',
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
                    'allow_repayment',
                    'allow_deferred_payment',
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
        if self.env.context.get('workflow_transition'):
            """
            When write is called with workflow_transition=True it means that all access verifications should be skipped.
            Trusting that they where done previously, right before the sudo().with_context(workflow_transition=True).write() call
            """
            return

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
