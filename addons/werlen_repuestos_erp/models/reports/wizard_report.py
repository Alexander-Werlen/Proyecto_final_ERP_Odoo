from odoo import models, fields, api
from datetime import datetime, time
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang

import logging

_logger = logging.getLogger(__name__)

class WizardReport(models.TransientModel):
    _name = 'wizard_report'
    _description = 'Asistente para generar informes'

    report_type = fields.Selection(
        [
            ('sales_by_seller', 'Ventas por Vendedor'),
            ('sales_by_client', 'Ventas por Cliente'),
            ('sales_by_payment_method', 'Ventas por Método de Pago'),
            ('sales_by_city', 'Ventas por Ciudad'),
            ('sales_by_withdrawer', 'Ventas por Quien Retira'),
            ('sales_by_point_of_sale', 'Ventas por Punto de Venta'),
            ('preparation_time_by_preparer', 'Tiempo de Preparación por Preparador'),
            ('sales_summary', 'Resumen de Ventas General'),
        ],
        string='Tipo de Informe',
        required=True,
        default='sales_by_seller'
    )

    date_preset = fields.Selection(
        [
            ('today', 'Hoy'),
            ('week', 'Esta semana'),
            ('month', 'Este mes'),
            ('year', 'Este año'),
            ('custom', 'Personalizado'),
        ],
        string='Período',
        required=True,
        default='today'
    )

    date_from = fields.Date(
        string='Desde',
        required=True
    )

    date_to = fields.Date(
        string='Hasta',
        required=True
    )

    @api.onchange('date_preset')
    def _onchange_date_preset(self):
        today = fields.Date.context_today(self)

        if self.date_preset == 'today':
            self.date_from = today
            self.date_to = today

        elif self.date_preset == 'week':
            self.date_from = today - relativedelta(days=today.weekday())
            self.date_to = today

        elif self.date_preset == 'month':
            self.date_from = today.replace(day=1)
            self.date_to = today

        elif self.date_preset == 'year':
            self.date_from = today.replace(month=1, day=1)
            self.date_to = today

        elif self.date_preset == 'custom':
            pass

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError("La fecha 'Desde' no puede ser mayor que la fecha 'Hasta'.")

    def action_generate(self):
        self.ensure_one()

        if self.report_type == 'sales_by_seller':
            return self._generate_sales_by_seller()
        elif self.report_type == 'sales_by_client':
            return self._generate_sales_by_client()
        elif self.report_type == 'sales_by_payment_method':
            return self._generate_sales_by_payment_method()
        elif self.report_type == 'sales_by_city':
            return self._generate_sales_by_city()
        elif self.report_type == 'sales_by_withdrawer':
            return self._generate_sales_by_withdrawer()
        elif self.report_type == 'sales_by_point_of_sale':
            return self._generate_sales_by_point_of_sale()
        elif self.report_type == 'preparation_time_by_preparer':
            return self._generate_preparation_time_by_preparer()
        elif self.report_type == 'sales_summary':
            return self._generate_sales_summary()

    def _get_date_domain(self):
        date_from_dt = datetime.combine(self.date_from, time.min)
        date_to_dt = datetime.combine(self.date_to, time.max)
        return [
            ('date', '>=', date_from_dt),
            ('date', '<=', date_to_dt),
        ]

    def _generate_sales_by_seller(self):
        domain = self._get_date_domain()

        sales_data = self.env['invoice_out'].read_group(
            domain=domain,
            fields=['billing_base_amount:sum'],
            groupby=['seller'],
        )

        credit_data = self.env['credit_note_out'].read_group(
            domain=domain,
            fields=['billing_base_amount:sum'],
            groupby=['seller_of_related_invoice'],
        )

        result_by_seller = {}

        for line in sales_data:
            if not line.get('seller'):
                continue

            seller_id = line['seller'][0]
            result_by_seller.setdefault(seller_id, {
                'seller_id': seller_id,
                'amount_invoices': 0,
                'amount_credit_notes': 0,
                'total_sold': 0.0,
                'total_credit': 0.0,
            })

            result_by_seller[seller_id]['total_sold'] += (
                line.get('billing_base_amount') or 0.0
            )
            result_by_seller[seller_id]['amount_invoices'] += (
                line.get('seller_count') or 0
            )

        for line in credit_data:
            if not line.get('seller_of_related_invoice'):
                continue

            seller_id = line['seller_of_related_invoice'][0]
            result_by_seller.setdefault(seller_id, {
                'seller_id': seller_id,
                'amount_invoices': 0,
                'amount_credit_notes': 0,
                'total_sold': 0.0,
                'total_credit': 0.0,
            })

            result_by_seller[seller_id]['total_credit'] += (
                line.get('billing_base_amount') or 0.0
            )
            result_by_seller[seller_id]['amount_credit_notes'] += (
                line.get('seller_of_related_invoice_count') or 0
            )

        summary_lines = []
        for data in result_by_seller.values():
            summary_lines.append({
                'seller_id': data['seller_id'],
                'amount_invoices': data['amount_invoices'],
                'amount_credit_notes': data['amount_credit_notes'],
                'total_sold': data['total_sold'],
                'total_credit': data['total_credit'],
                'balance': data['total_sold'] - data['total_credit'],
            })

        self.env['wizard_report_result_by_seller'].search([
            ('create_uid', '=', self.env.uid),
        ]).unlink()

        for data in summary_lines:
            self.env['wizard_report_result_by_seller'].create({
                'wizard_id': self.id,
                'seller_id': data['seller_id'],
                'amount_invoices': data['amount_invoices'],
                'amount_credit_notes': data['amount_credit_notes'],
                'total_sold': data['total_sold'],
                'total_credit': data['total_credit'],
                'balance': data['balance'],
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Ventas por Vendedor',
            'res_model': 'wizard_report_result_by_seller',
            'view_mode': 'list',
            'domain': [('wizard_id', '=', self.id)],
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_report_result_by_seller_list_view'
            ).id,
        }

    def _generate_sales_by_client(self):
        domain = self._get_date_domain()

        invoice_data = self.env['invoice_out'].read_group(
            domain=domain,
            fields=[
                'billing_base_amount:sum',
                'client',
            ],
            groupby=['client'],
        )

        account_invoice_data = self.env['invoice_out'].read_group(
            domain=domain + [('is_account_move', '=', True)],
            fields=['client'],
            groupby=['client'],
        )

        credit_data = self.env['credit_note_out'].read_group(
            domain=domain,
            fields=[
                'billing_base_amount:sum',
                'client',
            ],
            groupby=['client'],
        )

        result_by_client = {}

        for line in invoice_data:
            if not line.get('client'):
                continue

            client_id = line['client'][0]
            result_by_client.setdefault(client_id, {
                'client_id': client_id,
                'total_invoiced': 0.0,
                'total_credit_notes': 0.0,
                'invoice_count': 0,
                'credit_note_count': 0,
                'account_invoice_count': 0,
            })

            result_by_client[client_id]['total_invoiced'] += line.get('billing_base_amount') or 0.0
            result_by_client[client_id]['invoice_count'] += line.get('client_count') or 0

        for line in account_invoice_data:
            if not line.get('client'):
                continue
            client_id = line['client'][0]
            if client_id in result_by_client:
                result_by_client[client_id]['account_invoice_count'] += line.get('client_count') or 0

        for line in credit_data:
            if not line.get('client'):
                continue

            client_id = line['client'][0]
            result_by_client.setdefault(client_id, {
                'client_id': client_id,
                'total_invoiced': 0.0,
                'total_credit_notes': 0.0,
                'invoice_count': 0,
                'credit_note_count': 0,
                'account_invoice_count': 0,
            })

            result_by_client[client_id]['total_credit_notes'] += line.get('billing_base_amount') or 0.0
            result_by_client[client_id]['credit_note_count'] += line.get('client_count') or 0

        for data in result_by_client.values():
            data['net_amount'] = data['total_invoiced'] - data['total_credit_notes']
            if data['invoice_count'] > 0:
                data['account_percentage'] = (data['account_invoice_count'] / data['invoice_count']) * 100
            else:
                data['account_percentage'] = 0.0

        self.env['wizard_report_result_by_client'].search([
            ('create_uid', '=', self.env.uid),
        ]).unlink()

        for data in result_by_client.values():
            self.env['wizard_report_result_by_client'].create({
                'wizard_id': self.id,
                'client_id': data['client_id'],
                'total_invoiced': data['total_invoiced'],
                'total_credit_notes': data['total_credit_notes'],
                'net_amount': data['net_amount'],
                'invoice_count': data['invoice_count'],
                'credit_note_count': data['credit_note_count'],
                'account_percentage': data['account_percentage'],
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Ventas por Cliente',
            'res_model': 'wizard_report_result_by_client',
            'view_mode': 'list',
            'domain': [('wizard_id', '=', self.id)],
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_report_result_by_client_list_view'
            ).id,
        }

    def _generate_sales_by_payment_method(self):
        domain = self._get_date_domain()

        invoice_data = self.env['invoice_out'].read_group(
            domain=domain,
            fields=['billing_base_amount:sum'],
            groupby=['payment_method'],
        )

        total_invoiced_global = 0.0
        result_by_payment_method = {}

        for line in invoice_data:
            if not line.get('payment_method'):
                continue

            payment_method_id = line['payment_method'][0]
            total = line.get('billing_base_amount') or 0.0
            count = line.get('payment_method_count') or 0

            result_by_payment_method[payment_method_id] = {
                'payment_method_id': payment_method_id,
                'invoice_count': count,
                'total_invoiced': total,
            }
            total_invoiced_global += total

        self.env['wizard_report_result_by_payment_method'].search([
            ('create_uid', '=', self.env.uid),
        ]).unlink()

        for data in result_by_payment_method.values():
            percentage = (
                (data['total_invoiced'] / total_invoiced_global) * 100
                if total_invoiced_global else 0.0
            )
            self.env['wizard_report_result_by_payment_method'].create({
                'wizard_id': self.id,
                'payment_method_id': data['payment_method_id'],
                'invoice_count': data['invoice_count'],
                'total_invoiced': data['total_invoiced'],
                'percentage_of_total': percentage,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Ventas por Método de Pago',
            'res_model': 'wizard_report_result_by_payment_method',
            'view_mode': 'list',
            'domain': [('wizard_id', '=', self.id)],
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_report_result_by_payment_method_list_view'
            ).id,
        }

    def _generate_sales_by_city(self):
        domain = self._get_date_domain()

        invoice_data = self.env['invoice_out'].read_group(
            domain=domain,
            fields=['billing_base_amount:sum'],
            groupby=['city'],
        )

        result_by_city = {}

        for line in invoice_data:
            if not line.get('city'):
                continue

            city_id = line['city'][0]
            result_by_city[city_id] = {
                'city_id': city_id,
                'invoice_count': line.get('city_count') or 0,
                'total_invoiced': line.get('billing_base_amount') or 0.0,
            }

        self.env['wizard_report_result_by_city'].search([
            ('create_uid', '=', self.env.uid),
        ]).unlink()

        for data in result_by_city.values():
            self.env['wizard_report_result_by_city'].create({
                'wizard_id': self.id,
                'city_id': data['city_id'],
                'invoice_count': data['invoice_count'],
                'total_invoiced': data['total_invoiced'],
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Ventas por Ciudad',
            'res_model': 'wizard_report_result_by_city',
            'view_mode': 'list',
            'domain': [('wizard_id', '=', self.id)],
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_report_result_by_city_list_view'
            ).id,
        }

    def _generate_sales_by_withdrawer(self):
        domain = self._get_date_domain()

        order_data = self.env['sale_fulfillment_order'].read_group(
            domain=domain,
            fields=['total_cost:sum'],
            groupby=['who_withdraws'],
        )

        result_by_withdrawer = {}

        for line in order_data:
            if not line.get('who_withdraws'):
                continue

            withdrawer_id = line['who_withdraws'][0]
            result_by_withdrawer[withdrawer_id] = {
                'withdrawer_id': withdrawer_id,
                'order_count': line.get('who_withdraws_count') or 0,
                'total_cost': line.get('total_cost') or 0.0,
            }

        self.env['wizard_report_result_by_withdrawer'].search([
            ('create_uid', '=', self.env.uid),
        ]).unlink()

        for data in result_by_withdrawer.values():
            self.env['wizard_report_result_by_withdrawer'].create({
                'wizard_id': self.id,
                'withdrawer_id': data['withdrawer_id'],
                'order_count': data['order_count'],
                'total_cost': data['total_cost'],
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Ventas por Quien Retira',
            'res_model': 'wizard_report_result_by_withdrawer',
            'view_mode': 'list',
            'domain': [('wizard_id', '=', self.id)],
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_report_result_by_withdrawer_list_view'
            ).id,
        }

    def _generate_sales_by_point_of_sale(self):
        domain = self._get_date_domain()

        order_data = self.env['sale_fulfillment_order'].read_group(
            domain=domain,
            fields=['total_cost:sum'],
            groupby=['point_of_sale'],
        )

        result_by_point_of_sale = {}

        for line in order_data:
            if not line.get('point_of_sale'):
                continue

            point_of_sale_id = line['point_of_sale'][0]
            result_by_point_of_sale[point_of_sale_id] = {
                'point_of_sale_id': point_of_sale_id,
                'order_count': line.get('point_of_sale_count') or 0,
                'total_cost': line.get('total_cost') or 0.0,
            }

        self.env['wizard_report_result_by_point_of_sale'].search([
            ('create_uid', '=', self.env.uid),
        ]).unlink()

        for data in result_by_point_of_sale.values():
            self.env['wizard_report_result_by_point_of_sale'].create({
                'wizard_id': self.id,
                'point_of_sale_id': data['point_of_sale_id'],
                'order_count': data['order_count'],
                'total_cost': data['total_cost'],
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Ventas por Punto de Venta',
            'res_model': 'wizard_report_result_by_point_of_sale',
            'view_mode': 'list',
            'domain': [('wizard_id', '=', self.id)],
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_report_result_by_point_of_sale_list_view'
            ).id,
        }

    def _generate_preparation_time_by_preparer(self):
        self.ensure_one()
        domain_date_filter = self._get_date_domain()


        domain = domain_date_filter + [
            ('time_of_preparation_start', '!=', False),
            ('time_of_preparation_end', '!=', False),
            ('who_prepared', '!=', False),
        ]

        orders = self.env['sale_fulfillment_order'].search(domain)

        result_by_preparer = {}

        for order in orders:
            preparer_id = order.who_prepared.id
            if preparer_id not in result_by_preparer:
                result_by_preparer[preparer_id] = {
                    'preparer_id': preparer_id,
                    'total_invoices': 0,
                    'in_range_count': 0,
                    'total_minutes_in_range': 0.0,
                    'under_5_min_count': 0,
                    'over_4_hours_count': 0,
                }

            data = result_by_preparer[preparer_id]
            data['total_invoices'] += 1

            duration_seconds = (
                order.time_of_preparation_end - order.time_of_preparation_start
            ).total_seconds()
            duration_minutes = duration_seconds / 60.0

            if duration_minutes < 5:
                data['under_5_min_count'] += 1
            elif duration_minutes > 240:
                data['over_4_hours_count'] += 1
            else:
                data['in_range_count'] += 1
                data['total_minutes_in_range'] += duration_minutes

        self.env['wizard_report_result_by_preparer'].search([
            ('create_uid', '=', self.env.uid),
        ]).unlink()

        for data in result_by_preparer.values():
            avg_time = (
                data['total_minutes_in_range'] / data['in_range_count']
                if data['in_range_count'] > 0 else 0.0
            )
            self.env['wizard_report_result_by_preparer'].create({
                'wizard_id': self.id,
                'preparer_id': data['preparer_id'],
                'total_invoices': data['total_invoices'],
                'in_range_count': data['in_range_count'],
                'avg_preparation_time': avg_time,
                'under_5_min_count': data['under_5_min_count'],
                'over_4_hours_count': data['over_4_hours_count'],
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Tiempo de Preparación por Preparador',
            'res_model': 'wizard_report_result_by_preparer',
            'view_mode': 'list',
            'domain': [('wizard_id', '=', self.id)],
            'view_id': self.env.ref(
                'werlen_repuestos_erp.wizard_report_result_by_preparer_list_view'
            ).id,
        }

    def format_currency(self, amount):
        self.ensure_one()
        currency = self.env.company.currency_id
        formatted = formatLang(self.env, amount, currency_obj=currency)
        return formatted.replace('\xa0', ' ').replace('&nbsp;', ' ')

    def _generate_sales_summary(self):
        self.ensure_one()
        return self.env.ref(
            'werlen_repuestos_erp.action_report_sales_summary'
        ).report_action(self)

    def get_sales_summary_data(self):
        self.ensure_one()
        domain = self._get_date_domain()

        # --- Invoices (corrected and raw) ---
        cash_invoice_data = self.env['invoice_out'].read_group(
            domain=domain + [('is_account_move', '=', False)],
            fields=['billing_base_amount:sum', 'total_cost:sum'],
            groupby=[],
        )
        account_invoice_data = self.env['invoice_out'].read_group(
            domain=domain + [('is_account_move', '=', True)],
            fields=['billing_base_amount:sum', 'total_cost:sum'],
            groupby=[],
        )

        # --- Credit notes (corrected and raw) ---
        cash_credit_data = self.env['credit_note_out'].read_group(
            domain=domain + [('is_account_move', '=', False)],
            fields=['billing_base_amount:sum', 'total_amount:sum'],
            groupby=[],
        )
        account_credit_data = self.env['credit_note_out'].read_group(
            domain=domain + [('is_account_move', '=', True)],
            fields=['billing_base_amount:sum', 'total_amount:sum'],
            groupby=[],
        )

        # --- Discounts on receipts (Cuenta Corriente only; raw == corrected) ---
        account_discount_data = self.env['account_payment'].read_group(
            domain=domain + [('is_main_point_of_sale_category', '=', False)],
            fields=['discount_amount:sum'],
            groupby=[],
        )

        def _val(group, key, default=0.0):
            return group[0].get(key) or default if group else default

        cash_inv_corr = _val(cash_invoice_data, 'billing_base_amount')
        cash_inv_raw = _val(cash_invoice_data, 'total_cost')
        cash_inv_count = _val(cash_invoice_data, '__count', 0)

        account_inv_corr = _val(account_invoice_data, 'billing_base_amount')
        account_inv_raw = _val(account_invoice_data, 'total_cost')
        account_inv_count = _val(account_invoice_data, '__count', 0)

        cash_cn_corr = _val(cash_credit_data, 'billing_base_amount')
        cash_cn_raw = _val(cash_credit_data, 'total_amount')
        cash_cn_count = _val(cash_credit_data, '__count', 0)

        account_cn_corr = _val(account_credit_data, 'billing_base_amount')
        account_cn_raw = _val(account_credit_data, 'total_amount')
        account_cn_count = _val(account_credit_data, '__count', 0)

        account_discount_total = _val(account_discount_data, 'discount_amount')
        account_discount_count = _val(account_discount_data, '__count', 0)

        # --- Logistics (sale_fulfillment_order) ---
        total_orders = self.env['sale_fulfillment_order'].search_count(domain)

        pos_data = self.env['sale_fulfillment_order'].read_group(
            domain=domain,
            fields=['total_cost:sum'],
            groupby=['point_of_sale'],
        )

        pos_lines = []
        for line in pos_data:
            if not line.get('point_of_sale'):
                continue
            count = line.get('point_of_sale_count') or 0
            pos_lines.append({
                'name': line['point_of_sale'][1],
                'count': count,
                'percentage': (count / total_orders * 100) if total_orders else 0.0,
                'amount': line.get('total_cost') or 0.0,
            })

        delivery_data = self.env['sale_fulfillment_order'].read_group(
            domain=domain + [('has_delivery', '=', True)],
            fields=['total_cost:sum'],
            groupby=[],
        )
        delivery_count = _val(delivery_data, '__count', 0)
        delivery_amount = _val(delivery_data, 'total_cost')

        prep_data = self.env['sale_fulfillment_order'].read_group(
            domain=domain + [('is_asigned_to_preparation_team', '=', True)],
            fields=['total_cost:sum'],
            groupby=[],
        )
        prep_count = _val(prep_data, '__count', 0)
        prep_amount = _val(prep_data, 'total_cost')

        repayment_data = self.env['sale_fulfillment_order'].read_group(
            domain=domain + [('allow_repayment', '=', True)],
            fields=['total_cost:sum'],
            groupby=[],
        )
        repayment_count = _val(repayment_data, '__count', 0)
        repayment_amount = _val(repayment_data, 'total_cost')

        def _pct(count):
            return (count / total_orders * 100) if total_orders else 0.0

        # --- Matriz por categoría de Punto de Venta (Contado / Cuenta Corriente) ---
        # La categoría A identifica exclusivamente al punto de venta 0021;
        # cualquier otro código queda agrupado en la categoría B.
        matrix_categories = {
            'A': [('sales_point', '=', '0021')],
            'B': [
                '|',
                ('sales_point', '!=', '0021'),
                ('sales_point', '=', False),
            ],
        }
        matrix_columns = [('cash', 'Contado'), ('account', 'Cuenta Corriente')]

        def _sum(model, field, dom):
            res = self.env[model].read_group(
                domain=dom,
                fields=[f'{field}:sum'],
                groupby=[],
            )
            return (res[0].get(f'{field}') or 0.0) if res else 0.0

        matrix_cells = {}
        for category, category_domain in matrix_categories.items():
            for col_key, _ in matrix_columns:
                is_account = (col_key == 'account')
                base = domain + [
                    *category_domain,
                    ('is_account_move', '=', is_account),
                ]
                inv_sum = _sum('invoice_out', 'total_cost', base)
                cn_sum = _sum('credit_note_out', 'total_amount', base)
                if category == 'B' and is_account:
                    disc_sum = _sum(
                        'account_payment', 'discount_amount',
                        domain + [
                            ('is_main_point_of_sale_category', '=', False),
                            *category_domain,
                        ],
                    )
                else:
                    disc_sum = 0.0
                matrix_cells[(category, col_key)] = inv_sum - cn_sum - disc_sum

        matrix_row_totals = {
            category: sum(matrix_cells[(category, ck)] for ck, _ in matrix_columns)
            for category in matrix_categories
        }
        matrix_col_totals = {
            ck: sum(matrix_cells[(category, ck)] for category in matrix_categories)
            for ck, _ in matrix_columns
        }
        matrix_grand = sum(matrix_cells.values())

        matrix = {
            'categories': list(matrix_categories),
            'columns': matrix_columns,
            'cells': {f"{category}_{ck}": v for (category, ck), v in matrix_cells.items()},
            'row_totals': matrix_row_totals,
            'col_totals': matrix_col_totals,
            'grand': matrix_grand,
        }

        result = {
            'cash': {
                'invoice_amount': cash_inv_corr,
                'invoice_amount_raw': cash_inv_raw,
                'invoice_count': cash_inv_count,
                'credit_note_amount': cash_cn_corr,
                'credit_note_amount_raw': cash_cn_raw,
                'credit_note_count': cash_cn_count,
                'discount_amount': 0.0,
                'discount_count': 0,
                'net_sales': cash_inv_corr - cash_cn_corr,
                'net_sales_raw': cash_inv_raw - cash_cn_raw,
            },
            'account': {
                'invoice_amount': account_inv_corr,
                'invoice_amount_raw': account_inv_raw,
                'invoice_count': account_inv_count,
                'credit_note_amount': account_cn_corr,
                'credit_note_amount_raw': account_cn_raw,
                'credit_note_count': account_cn_count,
                'discount_amount': account_discount_total,
                'discount_count': account_discount_count,
                'net_sales': account_inv_corr - account_cn_corr - account_discount_total,
                'net_sales_raw': account_inv_raw - account_cn_raw - account_discount_total,
            },
            'total': {
                'invoice_amount': 0.0,
                'invoice_amount_raw': 0.0,
                'invoice_count': 0,
                'credit_note_amount': 0.0,
                'credit_note_amount_raw': 0.0,
                'credit_note_count': 0,
                'discount_amount': 0.0,
                'discount_count': 0,
                'net_sales': 0.0,
                'net_sales_raw': 0.0,
            },
            'logistics': {
                'total_orders': total_orders,
                'points_of_sale': pos_lines,
                'delivery_count': delivery_count,
                'delivery_amount': delivery_amount,
                'delivery_percentage': _pct(delivery_count),
                'preparation_count': prep_count,
                'preparation_amount': prep_amount,
                'preparation_percentage': _pct(prep_count),
                'repayment_count': repayment_count,
                'repayment_amount': repayment_amount,
                'repayment_percentage': _pct(repayment_count),
            },
            'matrix': matrix,
        }

        for key in ('cash', 'account'):
            for metric in result['total'].keys():
                result['total'][metric] += result[key][metric]

        return result
