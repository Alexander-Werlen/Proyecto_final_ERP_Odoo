from odoo import fields, models, tools


class AccountPaymentInAggregate(models.Model):
    _name = 'account_payment_in_aggregate'
    _description = 'Vista de pagos y cheques ingresados a cuenta corriente'
    _auto = False
    _order = 'date desc'

    source_model = fields.Char(string='Modelo origen', readonly=True)
    source_id = fields.Integer(string='ID origen', readonly=True)
    date = fields.Datetime(string='Fecha', readonly=True)
    origin_reason = fields.Selection(
        selection=[
            ('account_in', 'Ingreso a cuenta corriente'),
        ],
        string='Razón de origen',
        readonly=True,
    )
    partner_id = fields.Many2one('res.partner', string='Dueño del crédito', readonly=True)
    payment_method = fields.Char(string='Método de pago', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    original_amount = fields.Monetary(
        string='Importe original',
        currency_field='currency_id',
        readonly=True,
    )
    unreconciled_amount = fields.Monetary(
        string='Importe no reconciliado',
        currency_field='currency_id',
        readonly=True,
    )
    observations = fields.Text(string='Observaciones', readonly=True)
    payment_status = fields.Selection(
        selection=[
            ('not_paid', 'Pendiente'),
            ('partially_paid', 'Parcial'),
            ('paid', 'Total'),
            ('account', 'Cuenta Corriente'),
        ],
        string='Estado',
        readonly=True,
    )
    reference = fields.Char(string='Referencia', readonly=True)
    who_created = fields.Many2one('res.users', string='Creado por', readonly=True)

    def action_open_source(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Movimiento',
            'res_model': self.source_model,
            'res_id': self.source_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f'''
            CREATE VIEW {self._table} AS (
                SELECT
                    c.id AS id,
                    c.id AS source_id,
                    'check' AS source_model,
                    c.time_of_creation AS date,
                    c.payment_origin_explanation AS origin_reason,
                    c.owner_of_credit AS partner_id,
                    'CHEQUE' AS payment_method,
                    company.currency_id AS currency_id,
                    c.amount AS original_amount,
                    c.amount_not_reconciliated AS unreconciled_amount,
                    c.observations AS observations,
                    c.payment_status AS payment_status,
                    c.display_name AS reference,
                    c.who_created AS who_created
                FROM "check" c
                JOIN res_company company ON company.id = c.company_id
                WHERE c.payment_origin_explanation = 'account_in'

                UNION ALL

                SELECT
                    p.id + 1000000000 AS id,
                    p.id AS source_id,
                    'payment_line' AS source_model,
                    COALESCE(p.time_of_payment_confirmation, p.time_of_payment_proposal) AS date,
                    p.payment_origin_explanation AS origin_reason,
                    p.payer AS partner_id,
                    method.name AS payment_method,
                    company.currency_id AS currency_id,
                    p.amount AS original_amount,
                    p.amount_not_reconciliated AS unreconciled_amount,
                    p.observations AS observations,
                    p.payment_status AS payment_status,
                    p.name AS reference,
                    p.who_proposed_payment AS who_created
                FROM payment_line p
                LEFT JOIN payment_method method ON method.id = p.payment_method
                JOIN res_company company ON company.id = p.company_id
                WHERE p.payment_origin_explanation = 'account_in'
            )
        ''')
