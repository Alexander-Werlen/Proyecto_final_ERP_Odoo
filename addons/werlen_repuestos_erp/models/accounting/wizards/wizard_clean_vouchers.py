from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError

from ....utils.group_verification import ensure_user_in_groups


CONFIRMATION_TEXT_REQUIRED = 'LIMPIAR'
BATCH_SIZE = 200

LEGACY_IMPORT_PRESERVE_STATES = ('pending', 'processing')

VOUCHER_MODELS = (
    'invoice_out',
    'credit_note_out',
    'account_payment',
)

PAYMENT_MODELS = (
    'payment_line',
    'check',
)

ALL_RECONCILIATION_FK_FIELDS = (
    'invoice_out_id',
    'credit_note_out_id',
    'account_payment_id',
    'payment_line_in_id',
    'payment_line_out_id',
    'check_id',
)

VOUCHER_FK_FIELDS = (
    'invoice_out_id',
    'credit_note_out_id',
    'account_payment_id',
)

INCOMING_PAYMENT_FK_FIELDS = (
    'payment_line_in_id',
    'check_id',
)

OUTGOING_PAYMENT_FK_FIELDS = (
    'payment_line_out_id',
)

INCOMING_TO_OUTGOING = {
    'payment_line_in_id': 'payment_line',
    'payment_line_out_id': 'payment_line',
    'check_id': 'check',
    'invoice_out_id': 'invoice_out',
    'credit_note_out_id': 'credit_note_out',
    'account_payment_id': 'account_payment',
}

RECONCILIATION_FK_FIELDS_BY_MODEL = {
    'invoice_out': ('invoice_out_id',),
    'credit_note_out': ('credit_note_out_id',),
    'account_payment': ('account_payment_id',),
    'payment_line': ('payment_line_in_id', 'payment_line_out_id'),
    'check': ('check_id',),
}


class WizardCleanVouchers(models.TransientModel):
    _name = 'wizard.clean_vouchers'
    _description = 'Limpieza de Comprobantes por Punto de Venta'

    sales_point = fields.Char(
        string='Punto de Venta',
        required=True,
        size=4,
        help='Segmento de 4 dígitos del comprobante (ej. 0001).',
    )

    cutoff_date = fields.Date(
        string='Fecha de corte (inclusivo)',
        required=True,
        help='Se incluirán en la limpieza los comprobantes con fecha igual o anterior a este día (hasta 23:59:59).',
    )

    include_cash_sessions = fields.Boolean(
        string='Incluir cierres de caja cerrados',
        default=True,
    )

    confirmation_text = fields.Char(
        string='Confirmación',
        required=True,
        help=f'Debe escribir literalmente "{CONFIRMATION_TEXT_REQUIRED}" para habilitar la limpieza.',
    )

    has_executed = fields.Boolean(
        string='¿Ya se ejecutó?',
        default=False,
    )

    result_log = fields.Text(
        string='Resultado de la limpieza',
        readonly=True,
    )

    def _compute_cutoff_datetime(self):
        self.ensure_one()
        cutoff_date = fields.Date.to_date(self.cutoff_date)
        return fields.Datetime.to_datetime(cutoff_date) + timedelta(days=1) - timedelta(microseconds=1)

    def _check_group_system(self):
        ensure_user_in_groups(
            self.env.user,
            ['werlen_repuestos_erp.group_system'],
            error_message='Necesitas permisos de Sistema para ejecutar la limpieza.',
        )

    def _check_confirmation_text(self):
        self.ensure_one()
        if (self.confirmation_text or '').strip() != CONFIRMATION_TEXT_REQUIRED:
            raise UserError(
                f'Para ejecutar la limpieza debe escribir literalmente "{CONFIRMATION_TEXT_REQUIRED}" en el campo de confirmación.'
            )

    def _fetch_s0_vouchers(self, cutoff_dt):
        sp = self.sales_point
        invoices = self.env['invoice_out'].sudo().search([
            ('sales_point', '=', sp), ('date', '<=', cutoff_dt),
        ])
        credit_notes = self.env['credit_note_out'].sudo().search([
            ('sales_point', '=', sp), ('date', '<=', cutoff_dt),
        ])
        receipts = self.env['account_payment'].sudo().search([
            ('sales_point', '=', sp), ('date', '<=', cutoff_dt),
        ])
        return {
            'invoice_out': invoices,
            'credit_note_out': credit_notes,
            'account_payment': receipts,
        }

    def _fetch_s0_payments(self, cutoff_dt):
        Payment = self.env['payment_line'].sudo()
        Check = self.env['check'].sudo()
        payments = Payment.search([
            ('time_of_payment_confirmation', '!=', False),
            ('time_of_payment_confirmation', '<=', cutoff_dt),
        ])
        checks = Check.search([('time_of_creation', '<=', cutoff_dt)])
        return payments, checks

    def _fetch_s0_cash_sessions(self, cutoff_dt):
        return self.env['cash_session'].sudo().search([
            ('state', '=', 'closed'),
            ('closed_at', '!=', False),
            ('closed_at', '<=', cutoff_dt),
        ])

    def _fetch_s0_legacy_invoice_imports(self, cutoff_dt):
        return self.env['legacy_invoice_import'].sudo().search([
            ('create_date', '<=', cutoff_dt),
            ('state', 'not in', LEGACY_IMPORT_PRESERVE_STATES),
        ])

    def _get_node_key(self, model, record_id):
        return (model, record_id)

    def _get_reconciliation_neighbors(self, model, record_id):
        fk_fields = RECONCILIATION_FK_FIELDS_BY_MODEL.get(model, ())
        if not fk_fields:
            return []

        ReconciliationLine = self.env['reconciliation_line'].sudo()
        rl_records = ReconciliationLine
        for fk_field in fk_fields:
            rl_records |= ReconciliationLine.search([
                (fk_field, '=', record_id),
            ])

        neighbors = []
        for rl in rl_records:
            for other_field in ALL_RECONCILIATION_FK_FIELDS:
                other_value = getattr(rl, other_field, False)
                if not other_value:
                    continue
                other_id = other_value.id if hasattr(other_value, 'id') else other_value
                other_model = INCOMING_TO_OUTGOING[other_field]
                if other_model == model and other_id == record_id:
                    continue
                neighbors.append((other_model, other_id, rl.id))
        return neighbors

    def _bfs_components(self, s0_vouchers):
        initial_nodes = []
        for model_name in ('invoice_out', 'credit_note_out', 'account_payment'):
            for voucher in s0_vouchers.get(model_name, self.env[model_name]):
                initial_nodes.append(self._get_node_key(voucher._name, voucher.id))

        visited = set()
        components = []
        for start in initial_nodes:
            if start in visited:
                continue
            stack = [start]
            nodes = set()
            rls = set()
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                visited.add(node)
                nodes.add(node)
                model, record_id = node
                for other_model, other_id, rl_id in self._get_reconciliation_neighbors(
                    model,
                    record_id,
                ):
                    rls.add(rl_id)
                    other_key = self._get_node_key(other_model, other_id)
                    if other_key not in visited:
                        stack.append(other_key)
            components.append({'nodes': nodes, 'reconciliation_line_ids': rls})

        return components

    def _node_date(self, model, record_id):
        if model == 'invoice_out':
            rec = self.env['invoice_out'].sudo().browse(record_id)
            return rec.date if rec.exists() else False
        if model == 'credit_note_out':
            rec = self.env['credit_note_out'].sudo().browse(record_id)
            return rec.date if rec.exists() else False
        if model == 'account_payment':
            rec = self.env['account_payment'].sudo().browse(record_id)
            return rec.date if rec.exists() else False
        if model == 'payment_line':
            rec = self.env['payment_line'].sudo().browse(record_id)
            return rec.time_of_payment_confirmation if rec.exists() else False
        if model == 'check':
            rec = self.env['check'].sudo().browse(record_id)
            return rec.time_of_creation if rec.exists() else False
        return False

    def _classify_components(self, components, cutoff_dt):
        cleanup_components = []
        preserve_components = []
        for comp in components:
            out_of_scope = False
            for model, rid in comp['nodes']:
                d = self._node_date(model, rid)
                if d is False or d is None:
                    continue
                if d > cutoff_dt:
                    out_of_scope = True
                    break
            if out_of_scope:
                preserve_components.append(comp)
            else:
                cleanup_components.append(comp)
        return cleanup_components, preserve_components

    def _materialize_cleanup_sets(self, cleanup_components):
        invoice_outs = self.env['invoice_out']
        credit_notes = self.env['credit_note_out']
        account_payments = self.env['account_payment']
        payment_lines = self.env['payment_line']
        checks = self.env['check']
        reconciliation_line_ids = set()

        for comp in cleanup_components:
            reconciliation_line_ids |= comp['reconciliation_line_ids']
            for model, rid in comp['nodes']:
                if model == 'invoice_out':
                    invoice_outs |= self.env['invoice_out'].sudo().browse(rid)
                elif model == 'credit_note_out':
                    credit_notes |= self.env['credit_note_out'].sudo().browse(rid)
                elif model == 'account_payment':
                    account_payments |= self.env['account_payment'].sudo().browse(rid)
                elif model == 'payment_line':
                    payment_lines |= self.env['payment_line'].sudo().browse(rid)
                elif model == 'check':
                    checks |= self.env['check'].sudo().browse(rid)

        return {
            'invoice_out': invoice_outs,
            'credit_note_out': credit_notes,
            'account_payment': account_payments,
            'payment_line': payment_lines,
            'check': checks,
            'reconciliation_line_ids': reconciliation_line_ids,
        }

    def _materialize_preserved_node_keys(self, preserve_components):
        keys = set()
        for comp in preserve_components:
            for model, rid in comp['nodes']:
                keys.add(self._get_node_key(model, rid))
        return keys

    def _compute_orphans(self, s0_payments, s0_checks, preserved_keys):
        orphan_payments = self.env['payment_line']
        orphan_checks = self.env['check']
        for p in s0_payments:
            if self._get_node_key('payment_line', p.id) in preserved_keys:
                continue
            if not p.reconciliation_lines:
                orphan_payments |= p
        for c in s0_checks:
            if self._get_node_key('check', c.id) in preserved_keys:
                continue
            if not c.reconciliation_lines:
                orphan_checks |= c
        return orphan_payments, orphan_checks

    def _collect_sale_fulfillment_orders(self, invoice_outs):
        if not invoice_outs:
            return self.env['sale_fulfillment_order']
        return self.env['sale_fulfillment_order'].sudo().search([
            ('invoice_id', 'in', invoice_outs.ids),
        ])

    def _collect_client_claims_referencing_cleaned_records(
        self,
        sfo_to_clean,
        credit_notes_to_clean,
    ):
        ClientClaim = self.env['client_claim'].sudo()
        claims = ClientClaim

        if sfo_to_clean:
            claims |= ClientClaim.search([
                '|',
                ('sale_fulfillment_order_id', 'in', sfo_to_clean.ids),
                ('resolution_sale_fulfillment_order_id', 'in', sfo_to_clean.ids),
            ])
        if credit_notes_to_clean:
            claims |= ClientClaim.search([
                ('resolution_credit_note_id', 'in', credit_notes_to_clean.ids),
            ])

        return claims

    def _clear_client_claim_references(
        self,
        sfo_to_clean,
        credit_notes_to_clean,
    ):
        claims = self._collect_client_claims_referencing_cleaned_records(
            sfo_to_clean,
            credit_notes_to_clean,
        )
        if not claims:
            return 0

        sfo_ids = set(sfo_to_clean.ids)
        credit_note_ids = set(credit_notes_to_clean.ids)
        for claim in claims:
            vals = {}
            if claim.sale_fulfillment_order_id.id in sfo_ids:
                vals['sale_fulfillment_order_id'] = False
            if claim.resolution_sale_fulfillment_order_id.id in sfo_ids:
                vals['resolution_sale_fulfillment_order_id'] = False
            if claim.resolution_credit_note_id.id in credit_note_ids:
                vals['resolution_credit_note_id'] = False

            if vals:
                claim.with_context(
                    workflow_transition=True,
                    tracking_disable=True,
                ).write(vals)

        return len(claims)

    def _collect_supplier_payments_referencing_checks(self, checks_to_clean):
        if not checks_to_clean:
            return self.env['supplier_payment']
        return self.env['supplier_payment'].sudo().search([
            ('check_ids', 'in', checks_to_clean.ids),
        ])

    def _detach_checks_from_supplier_payments(self, checks_to_clean):
        payments = self._collect_supplier_payments_referencing_checks(
            checks_to_clean,
        )
        if not payments:
            return 0

        check_ids = set(checks_to_clean.ids)
        detached_links = 0
        for payment in payments:
            payment_check_ids = set(payment.check_ids.ids) & check_ids
            if not payment_check_ids:
                continue
            payment.with_context(tracking_disable=True).write({
                'check_ids': [
                    (3, check_id, 0) for check_id in payment_check_ids
                ],
            })
            detached_links += len(payment_check_ids)

        return detached_links

    def _disable_credit_note_requirement(self, cutoff_dt):
        self.ensure_one()
        sfo_to_relax = self.env['sale_fulfillment_order'].sudo().search([
            ('must_determine_related_credit_notes', '=', True),
            ('date', '!=', False),
            ('date', '<=', cutoff_dt),
        ])
        if not sfo_to_relax:
            return 0
        sfo_to_relax.with_context(workflow_transition=True).write({
            'must_determine_related_credit_notes': False,
        })
        return len(sfo_to_relax)

    def _count_sfo_to_relax(self, cutoff_dt):
        self.ensure_one()
        return self.env['sale_fulfillment_order'].sudo().search_count([
            ('must_determine_related_credit_notes', '=', True),
            ('date', '!=', False),
            ('date', '<=', cutoff_dt),
        ])

    def _fix_cash_session_chains(self, cs_to_clean):
        Journal = self.env['journal'].sudo()
        if not cs_to_clean:
            return 0

        fixed = 0
        for journal in Journal.search([('id', 'in', cs_to_clean.mapped('journal_id').ids)]):
            all_sessions_for_journal = self.env['cash_session'].sudo().search([
                ('journal_id', '=', journal.id),
                ('state', '=', 'closed'),
            ], order='closed_at asc')
            cleaned_ids = set(cs_to_clean.filtered(lambda s: s.journal_id == journal).ids)
            survivors = all_sessions_for_journal.filtered(lambda s: s.id not in cleaned_ids)

            for survivor in survivors.sorted('closed_at'):
                current_prev_id = survivor.previous_session.id if survivor.previous_session else False
                if current_prev_id not in cleaned_ids:
                    continue

                previous_survivors = survivors.filtered(
                    lambda s: s.closed_at and s.closed_at <= survivor.closed_at and s.id != survivor.id
                ).sorted('closed_at', reverse=True)
                new_prev = previous_survivors[:1]
                new_prev_id = new_prev.id if new_prev else False

                survivor.with_context(cash_session_reopen=True).sudo().write({
                    'previous_session': new_prev_id,
                })
                fixed += 1

            for cs in cs_to_clean.filtered(lambda s: s.journal_id == journal):
                if journal.current_cash_session and journal.current_cash_session.id == cs.id:
                    journal.sudo().write({'current_cash_session': False})
        return fixed

    def _chunked_cleanup(self, records, model_label='records'):
        if not records:
            return 0
        ids = records.ids
        total = len(ids)
        cleaned = 0
        ctx = {
            'workflow_transition': True,
            'tracking_disable': True,
            'cash_session_reopen': True,
            'cleanup_vouchers': True,
        }
        skip_commit = self.env.context.get('cleanup_skip_commit', False)
        for i in range(0, total, BATCH_SIZE):
            batch_ids = ids[i:i + BATCH_SIZE]
            with self.env.cr.savepoint():
                batch = records.browse(batch_ids)
                batch.with_context(**ctx).sudo().unlink()
            if not skip_commit:
                self.env.cr.commit()
            cleaned += len(batch_ids)
            _ = model_label
        return cleaned

    def _run_cleanup(self):
        self.ensure_one()
        self._check_group_system()
        self._check_confirmation_text()
        if self.has_executed:
            raise UserError('Este wizard ya fue ejecutado. Cree uno nuevo desde el menú.')

        cutoff_dt = self._compute_cutoff_datetime()
        sp = self.sales_point

        s0_vouchers = self._fetch_s0_vouchers(cutoff_dt)
        s0_payments, s0_checks = self._fetch_s0_payments(cutoff_dt)
        cs_to_clean = self._fetch_s0_cash_sessions(cutoff_dt) if self.include_cash_sessions else self.env['cash_session']
        lii_to_clean = self._fetch_s0_legacy_invoice_imports(cutoff_dt)

        log_lines = []
        log_lines.append(f'Punto de venta: {sp}')
        log_lines.append(f'Fecha de corte (inclusive): {self.cutoff_date.isoformat()} ({cutoff_dt})')
        log_lines.append(f'Cierres de caja: {"INCLUIDOS" if self.include_cash_sessions else "NO INCLUIDOS"}')
        log_lines.append('')
        log_lines.append(f'Vouchers target (S0):')
        log_lines.append(f'  invoice_out: {len(s0_vouchers["invoice_out"])}')
        log_lines.append(f'  credit_note_out: {len(s0_vouchers["credit_note_out"])}')
        log_lines.append(f'  account_payment: {len(s0_vouchers["account_payment"])}')
        log_lines.append(f'Payment lines in-scope: {len(s0_payments)}')
        log_lines.append(f'Checks in-scope: {len(s0_checks)}')
        log_lines.append(f'Cash sessions in-scope: {len(cs_to_clean)}')
        log_lines.append(f'Legacy invoice imports in-scope: {len(lii_to_clean)}')
        log_lines.append('')

        components = self._bfs_components(s0_vouchers)
        log_lines.append(f'Componentes conexos (grafo): {len(components)}')
        cleanup_components, preserve_components = self._classify_components(components, cutoff_dt)
        log_lines.append(f'  A limpiar: {len(cleanup_components)}')
        log_lines.append(f'  A preservar: {len(preserve_components)}')
        log_lines.append('')

        cleanup_sets = self._materialize_cleanup_sets(cleanup_components)
        preserved_keys = self._materialize_preserved_node_keys(preserve_components)
        orphan_payments, orphan_checks = self._compute_orphans(
            s0_payments, s0_checks, preserved_keys,
        )
        sfo_to_clean = self._collect_sale_fulfillment_orders(cleanup_sets['invoice_out'])

        checks_to_clean = self.env['check'].sudo().browse(
            list(set(cleanup_sets['check'].ids) | set(orphan_checks.ids))
        )
        client_claims_to_clear = self._collect_client_claims_referencing_cleaned_records(
            sfo_to_clean,
            cleanup_sets['credit_note_out'],
        )
        supplier_payments_to_update = self._collect_supplier_payments_referencing_checks(
            checks_to_clean,
        )

        log_lines.append(f'Reconciliation lines a limpiar: {len(cleanup_sets["reconciliation_line_ids"])}')
        log_lines.append(f'Invoice out a limpiar: {len(cleanup_sets["invoice_out"])}')
        log_lines.append(f'Credit note out a limpiar: {len(cleanup_sets["credit_note_out"])}')
        log_lines.append(f'Account payment a limpiar: {len(cleanup_sets["account_payment"])}')
        log_lines.append(f'Payment line a limpiar (grafo + huérfanos): {len(cleanup_sets["payment_line"]) + len(orphan_payments)}')
        log_lines.append(f'Check a limpiar (grafo + huérfanos): {len(cleanup_sets["check"]) + len(orphan_checks)}')
        log_lines.append(f'Sale fulfillment order a limpiar: {len(sfo_to_clean)}')
        log_lines.append(f'Client claims con referencias a limpiar: {len(client_claims_to_clear)}')
        log_lines.append(f'Pagos a proveedor con cheques a desvincular: {len(supplier_payments_to_update)}')
        log_lines.append(f'Cash sessions a limpiar: {len(cs_to_clean)}')
        log_lines.append(f'Legacy invoice imports a limpiar: {len(lii_to_clean)}')
        log_lines.append('')

        fixed_chains = self._fix_cash_session_chains(cs_to_clean)
        log_lines.append(f'Cadenas de cash_session reparadas: {fixed_chains}')

        relaxed = self._disable_credit_note_requirement(cutoff_dt)
        log_lines.append(f'Sale fulfillment order con "Obligar NC" desactivado: {relaxed}')

        claims_cleared = self._clear_client_claim_references(
            sfo_to_clean,
            cleanup_sets['credit_note_out'],
        )
        log_lines.append(f'[OK] Referencias de client_claim limpiadas: {claims_cleared}')

        detached_links = self._detach_checks_from_supplier_payments(
            checks_to_clean,
        )
        log_lines.append(
            f'[OK] Vínculos check-pago a proveedor limpiados: {detached_links}'
        )

        if cleanup_sets['reconciliation_line_ids']:
            rl_records = self.env['reconciliation_line'].sudo().browse(list(cleanup_sets['reconciliation_line_ids']))
            n = self._chunked_cleanup(rl_records, 'reconciliation_line')
            log_lines.append(f'[OK] reconciliation_line limpiadas: {n}')

        if cs_to_clean:
            n = self._chunked_cleanup(cs_to_clean, 'cash_session')
            log_lines.append(f'[OK] cash_session limpiadas: {n}')

        if sfo_to_clean:
            n = self._chunked_cleanup(sfo_to_clean, 'sale_fulfillment_order')
            log_lines.append(f'[OK] sale_fulfillment_order limpiadas: {n}')

        if lii_to_clean:
            n = self._chunked_cleanup(lii_to_clean, 'legacy_invoice_import')
            log_lines.append(f'[OK] legacy_invoice_import limpiados: {n}')

        for model_name in ('invoice_out', 'credit_note_out', 'account_payment'):
            recs = cleanup_sets[model_name]
            n = self._chunked_cleanup(recs, model_name)
            log_lines.append(f'[OK] {model_name} limpiados: {n}')

        if cleanup_sets['payment_line']:
            n = self._chunked_cleanup(cleanup_sets['payment_line'], 'payment_line')
            log_lines.append(f'[OK] payment_line (grafo) limpiados: {n}')
        if orphan_payments:
            n = self._chunked_cleanup(orphan_payments, 'orphan payment_line')
            log_lines.append(f'[OK] payment_line (huérfanos) limpiados: {n}')

        if cleanup_sets['check']:
            n = self._chunked_cleanup(cleanup_sets['check'], 'check')
            log_lines.append(f'[OK] check (grafo) limpiados: {n}')
        if orphan_checks:
            n = self._chunked_cleanup(orphan_checks, 'orphan check')
            log_lines.append(f'[OK] check (huérfanos) limpiados: {n}')

        self.env.cr.execute("""
            SELECT COUNT(*) FROM reconciliation_line rl
            WHERE
                (rl.invoice_out_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM invoice_out i WHERE i.id = rl.invoice_out_id))
             OR (rl.credit_note_out_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM credit_note_out c WHERE c.id = rl.credit_note_out_id))
             OR (rl.account_payment_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM account_payment a WHERE a.id = rl.account_payment_id))
             OR (rl.payment_line_in_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM payment_line p WHERE p.id = rl.payment_line_in_id))
             OR (rl.payment_line_out_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM payment_line p2 WHERE p2.id = rl.payment_line_out_id))
             OR (rl.check_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "check" k WHERE k.id = rl.check_id))
        """)
        dangling = self.env.cr.fetchone()[0] or 0
        if dangling:
            raise UserError(
                f'Validación posterior a la limpieza FALLÓ: quedaron {dangling} reconciliation_line con FKs colgadas.'
            )
        log_lines.append('[OK] Validación posterior a la limpieza: 0 reconciliaciones colgadas.')

        log_lines.append('')
        log_lines.append('=== LIMPIEZA COMPLETADA ===')

        self.write({
            'has_executed': True,
            'result_log': '\n'.join(log_lines),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.clean_vouchers',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('werlen_repuestos_erp.wizard_bulk_delete_vouchers_result_view').id,
            'target': 'new',
            'name': 'Resultado de la Limpieza',
        }

    def action_execute(self):
        return self._run_cleanup()

    def action_preview(self):
        self.ensure_one()
        self._check_group_system()

        cutoff_dt = self._compute_cutoff_datetime()
        s0_vouchers = self._fetch_s0_vouchers(cutoff_dt)
        s0_payments, s0_checks = self._fetch_s0_payments(cutoff_dt)
        cs_to_clean = self._fetch_s0_cash_sessions(cutoff_dt) if self.include_cash_sessions else self.env['cash_session']
        lii_to_clean = self._fetch_s0_legacy_invoice_imports(cutoff_dt)

        components = self._bfs_components(s0_vouchers)
        cleanup_components, preserve_components = self._classify_components(components, cutoff_dt)
        cleanup_sets = self._materialize_cleanup_sets(cleanup_components)
        preserved_keys = self._materialize_preserved_node_keys(preserve_components)
        orphan_payments, orphan_checks = self._compute_orphans(
            s0_payments, s0_checks, preserved_keys,
        )
        sfo_to_clean = self._collect_sale_fulfillment_orders(cleanup_sets['invoice_out'])
        checks_to_clean = self.env['check'].sudo().browse(
            list(set(cleanup_sets['check'].ids) | set(orphan_checks.ids))
        )
        client_claims_to_clear = self._collect_client_claims_referencing_cleaned_records(
            sfo_to_clean,
            cleanup_sets['credit_note_out'],
        )
        supplier_payments_to_update = self._collect_supplier_payments_referencing_checks(
            checks_to_clean,
        )

        lines = [
            f'Punto de venta: {self.sales_point}',
            f'Fecha de corte: {self.cutoff_date.isoformat()} (inclusivo)',
            f'Cierres de caja: {"INCLUIDOS" if self.include_cash_sessions else "NO INCLUIDOS"}',
            '',
            'Vouchers target (S0):',
            f'  invoice_out (sales_point=match, date<=cutoff): {len(self.env["invoice_out"].sudo().search([("sales_point","=",self.sales_point),("date","<=",cutoff_dt)]))}',
            f'  credit_note_out (sales_point=match, date<=cutoff): {len(self.env["credit_note_out"].sudo().search([("sales_point","=",self.sales_point),("date","<=",cutoff_dt)]))}',
            f'  account_payment (sales_point=match, date<=cutoff): {len(self.env["account_payment"].sudo().search([("sales_point","=",self.sales_point),("date","<=",cutoff_dt)]))}',
            '',
            f'Componentes conexos: {len(components)}',
            f'  A limpiar: {len(cleanup_components)}',
            f'  A preservar: {len(preserve_components)}',
            '',
            'Registros a limpiar (componentes):',
            f'  invoice_out: {len(cleanup_sets["invoice_out"])}',
            f'  credit_note_out: {len(cleanup_sets["credit_note_out"])}',
            f'  account_payment: {len(cleanup_sets["account_payment"])}',
            f'  payment_line: {len(cleanup_sets["payment_line"])}',
            f'  check: {len(cleanup_sets["check"])}',
            f'  reconciliation_line: {len(cleanup_sets["reconciliation_line_ids"])}',
            '',
            'Huérfanos (in-scope, sin reconciliaciones o solo en comp. a limpiar):',
            f'  payment_line: {len(orphan_payments)}',
            f'  check: {len(orphan_checks)}',
            '',
            'Otros:',
            f'  sale_fulfillment_order: {len(sfo_to_clean)}',
            f'  client_claim referencias a limpiar: {len(client_claims_to_clear)}',
            f'  supplier_payment con cheques a desvincular: {len(supplier_payments_to_update)}',
            f'  cash_session: {len(cs_to_clean)}',
            f'  legacy_invoice_import: {len(lii_to_clean)}',
            f'  SFO con "Obligar NC" a desactivar: {self._count_sfo_to_relax(cutoff_dt)}',
        ]

        self.write({
            'result_log': '\n'.join(lines) + '\n\n(Esto es una previsualización. No se limpió nada todavía. Escriba LIMPIAR y pulse "Ejecutar limpieza" para confirmar.)',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.clean_vouchers',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('werlen_repuestos_erp.wizard_bulk_delete_vouchers_result_view').id,
            'target': 'new',
            'name': 'Previsualización de Limpieza',
        }
