from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from ...enums.purchases.supplier_claim_state import SUPPLIER_CLAIM_STATE_ENUM
from ...enums.purchases.supplier_claim_type import SUPPLIER_CLAIM_TYPE_ENUM
from ...utils.group_verification import ensure_user_in_groups


CLAIM_MANAGE_GROUPS = [
    'werlen_repuestos_erp.group_administration',
]


class SupplierClaim(models.Model):
    _name = 'supplier_claim'
    _description = 'Reclamo a proveedor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'creation_date desc, id desc'

    name = fields.Char(string='Identificador', required=True, readonly=True,
                       index=True, copy=False, default='Nuevo')
    claim_type = fields.Selection(SUPPLIER_CLAIM_TYPE_ENUM, string='Tipo de reclamo',
                                  required=True, readonly=True, tracking=True)
    supplier_id = fields.Many2one('res.partner', string='Proveedor', required=True,
                                  tracking=True, domain=[('is_supplier', '=', True)])
    product_id = fields.Many2one('purchase.product', string='Producto', required=True,
                                 readonly=True, tracking=True)
    list_price = fields.Monetary(string='Precio de lista', currency_field='currency_id',
                                 readonly=True, tracking=True)
    observations = fields.Text(string='Observaciones', tracking=True)
    state = fields.Selection(SUPPLIER_CLAIM_STATE_ENUM, string='Estado', default='open',
                             required=True, readonly=True, index=True, tracking=True)
    purchase_invoice_id = fields.Many2one('purchase_invoice', string='Factura de compra',
                                          readonly=True, tracking=True)
    reception_id = fields.Many2one('reception', string='Ingreso de mercadería',
                                   readonly=True, tracking=True)
    client_claim_id = fields.Many2one('client_claim', string='Reclamo de cliente',
                                      readonly=True, tracking=True)
    return_line_ids = fields.One2many('return_line', 'claim_id', string='Líneas de devolución',
                                      readonly=True)
    active_return_line_id = fields.Many2one('return_line', string='Línea activa', readonly=True)
    who_created_id = fields.Many2one('res.users', string='Creado por',
                                     default=lambda self: self.env.user, readonly=True)
    resolution_observations = fields.Text(string='Descripción de resolución', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía',
                                 default=lambda self: self.env.user.company_id, readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    creation_date = fields.Datetime(string='Fecha de creación', default=fields.Datetime.now,
                                    required=True, readonly=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('supplier.claim')
        return super().create(vals_list)

    def _check_manage_permission(self):
        ensure_user_in_groups(self.env.user, CLAIM_MANAGE_GROUPS,
                              error_message='No tiene permisos para gestionar reclamos a proveedor.')

    def _log_action(self, action):
        self.ensure_one()
        timestamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        self.message_post(
            body=Markup(
                '<ul style="margin:0;padding-left:16px;">'
                f'<li><b>Acción:</b> {action}</li>'
                f'<li><b>Usuario:</b> {self.env.user.name}</li>'
                f'<li><b>Fecha:</b> {timestamp:%Y-%m-%d %H:%M:%S}</li>'
                '</ul>'
            ),
            message_type='comment', subtype_xmlid='mail.mt_note',
        )

    def action_start_progress(self):
        self.ensure_one()
        self._check_manage_permission()
        if self.state != 'open':
            raise UserError('Solo se puede iniciar la gestión desde un reclamo abierto.')
        self.sudo().write({'state': 'in_progress'})
        self._log_action('Inició la gestión del reclamo.')

    def action_resolve(self):
        self.ensure_one()
        self._check_manage_permission()
        if self.state not in ('open', 'in_progress'):
            raise UserError('Solo se puede resolver un reclamo abierto o en gestión.')
        self.sudo().write({'state': 'resolved'})
        self._log_action('Resolvió el reclamo.')

    def action_reject(self):
        self.ensure_one()
        self._check_manage_permission()
        if self.state not in ('open', 'in_progress'):
            raise UserError('Solo se puede rechazar un reclamo abierto o en gestión.')
        self.sudo().write({'state': 'rejected'})
        self._log_action('Rechazó el reclamo.')

    def action_reopen(self):
        self.ensure_one()
        self._check_manage_permission()
        if self.state not in ('resolved', 'rejected'):
            raise UserError('Solo se puede reabrir un reclamo resuelto o rechazado.')
        self.sudo().write({'state': 'open', 'resolution_observations': False})
        self._log_action('Reabrió el reclamo.')

    @api.model
    def get_claims_returns_dashboard_data(self):
        self = self.sudo()

        active_claims = self.search([
            ('state', 'in', ('open', 'in_progress')),
        ])
        active_returns = self.env['return_note'].search([
            ('state', 'in', ('draft', 'prepared', 'sent')),
        ])

        return_state_selection = dict(
            self.env['return_note']._fields['state'].selection
        )

        supplier_map = {}

        for claim in active_claims:
            sid = claim.supplier_id.id
            if sid not in supplier_map:
                supplier_map[sid] = {
                    'id': sid,
                    'name': claim.supplier_id.name,
                    'open_claims_raw': [],
                    'in_progress_claims_raw': [],
                    'open_returns': [],
                }
            key = 'open_claims_raw' if claim.state == 'open' else 'in_progress_claims_raw'
            supplier_map[sid][key].append(claim)

        for ret in active_returns:
            sid = ret.supplier_id.id
            if sid not in supplier_map:
                supplier_map[sid] = {
                    'id': sid,
                    'name': ret.supplier_id.name,
                    'open_claims_raw': [],
                    'in_progress_claims_raw': [],
                    'open_returns': [],
                }
            supplier_map[sid]['open_returns'].append({
                'id': ret.id,
                'name': ret.name,
                'state': ret.state,
                'state_label': return_state_selection.get(ret.state, ret.state),
            })

        claim_type_label = {
            'missing': 'Faltante',
            'excess': 'Sobrante',
            'defective': 'Defectuoso',
            'return_claim': 'Devolución',
            'warranty': 'Garantía',
        }

        def _truncate_obs(raw):
            if not raw:
                return ''
            text = raw.strip()
            sep_idx = text.find('-----')
            if sep_idx != -1:
                text = text[:sep_idx].strip()
            if len(text) > 200:
                text = text[:200] + '...'
            return text

        def _build_claims_section(raw_claims):
            product_type_map = {}
            for claim in raw_claims:
                ct = claim.claim_type
                pid = claim.product_id.id
                pcode = claim.product_id.name
                pname = claim.product_id.description or ''
                obs = _truncate_obs(claim.observations)

                if ct not in product_type_map:
                    product_type_map[ct] = {}
                if pid not in product_type_map[ct]:
                    product_type_map[ct][pid] = {
                        'id': pid,
                        'code': pcode,
                        'name': pname,
                        'observations': [],
                    }
                product_type_map[ct][pid]['observations'].append(obs)

            result = []
            for ct in ['missing', 'excess', 'defective', 'return_claim', 'warranty']:
                if ct not in product_type_map:
                    continue
                products = []
                for pid, pdata in product_type_map[ct].items():
                    obs_list = pdata['observations']
                    unique = set(obs_list)
                    if len(unique) == 1:
                        common_obs = obs_list[0] or None
                    else:
                        common_obs = False

                    products.append({
                        'id': pdata['id'],
                        'code': pdata['code'],
                        'name': pdata['name'],
                        'count': len(pdata['observations']),
                        'common_observation': common_obs,
                    })

                products.sort(key=lambda p: (-p['count'], p['code']))

                result.append({
                    'claim_type': ct,
                    'claim_type_label': claim_type_label.get(ct, ct),
                    'count': sum(p['count'] for p in products),
                    'products': products,
                })

            return result

        suppliers = []
        for sid, sdata in supplier_map.items():
            open_claims = _build_claims_section(sdata['open_claims_raw'])
            in_progress_claims = _build_claims_section(sdata['in_progress_claims_raw'])
            open_total = sum(g['count'] for g in open_claims)
            in_progress_total = sum(g['count'] for g in in_progress_claims)
            returns_total = len(sdata['open_returns'])

            total_activity = open_total + in_progress_total + returns_total

            suppliers.append({
                'id': sdata['id'],
                'name': sdata['name'],
                'open_claims': open_claims,
                'in_progress_claims': in_progress_claims,
                'open_returns': sdata['open_returns'],
                '_total_activity': total_activity,
                '_open_claims_total': open_total,
                '_in_progress_claims_total': in_progress_total,
                '_returns_total': returns_total,
            })

        suppliers.sort(key=lambda s: ((s['name'] or '').casefold(), s['id']))

        return {'suppliers': suppliers}
