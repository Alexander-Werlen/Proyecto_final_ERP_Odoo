/** @odoo-module **/

import { Component, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

import { formatMonetary } from "@web/views/fields/formatters";

export class AccountantDashboard extends Component {

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.formatAmount = (amount) => {
            return formatMonetary(amount, {
                currencyId: session.company_currency_id,
            });
        };

        this.state = useState({
            columns: [],
            userName: session.partner_display_name || "",
            unreconciledCreditNotesCount: 0,
            payments: [],
            journals: [],
            selectedJournalId: null,
            sessionInfo: { has_open_session: false, is_over_24h: false, hours_open: 0, session_id: false },
            selectedJournalName: "",
            loading: true,
            isFirstLoad: false,
        });

        this._hasLoaded = false;

        this.loadData();
        this.interval = setInterval(() => this.loadData(), 10000);
        onWillUnmount(() => clearInterval(this.interval));
    }

    async loadData() {

        if (!this._hasLoaded) {
            this.state.loading = true;
        }

        // get journals (only once)
        if (this.state.selectedJournalId === null) {

            const result = await this.orm.call(
                "payment_line",
                "get_available_journals",
                []
            );

            this.state.journals = result.journals;

            if (!this.state.selectedJournalId) {
                this.state.selectedJournalId =
                    result.default_journal_id ||
                    (result.journals.length ? result.journals[0].id : null);
            }
        }

        // Invoices info
        const result = await this.orm.call(
            "sale_fulfillment_order",
            "get_accountant_dashboard_data",
            []
        );

        result.columns.forEach(col => {
            col.segments.forEach((seg, idx, arr) => {
                seg.height = col.total
                    ? (seg.count / col.total) * 100
                    : 0;
                seg.zIndex = arr.length - idx;
            });
        });

        this.state.columns = result.columns;
        this.state.unreconciledCreditNotesCount = result.unreconciled_credit_notes_count || 0;

        const selectedJournal = this.state.journals.find(
            j => j.id === this.state.selectedJournalId
        );
        this.state.selectedJournalName = selectedJournal ? selectedJournal.name : "";

        // Session info
        if (this.state.selectedJournalId) {
            const sessionInfo = await this.orm.call(
                "journal",
                "get_dashboard_session_info",
                [[this.state.selectedJournalId]]
            );
            this.state.sessionInfo = sessionInfo;
        } else {
            this.state.sessionInfo = { has_open_session: false, is_over_24h: false, hours_open: 0, session_id: false };
        }

        // Payments info
        const payments = await this.orm.call(
            "payment_line",
            "get_cashier_today_payments",
            [this.state.selectedJournalId]
        );

        this.state.payments = payments;

        this.state.loading = false;

        const isFirst = !this._hasLoaded;
        this._hasLoaded = true;

        if (isFirst) {
            this.state.isFirstLoad = true;
            setTimeout(() => {
                this.state.isFirstLoad = false;
            }, 1200);
        }
    }

    onOpenPayment = (payment) => {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "payment_line",
            res_id: payment.id,
            views: [[false, "form"]],
        });
    };

    onJournalChange(ev) {
        this.state.selectedJournalId = parseInt(ev.target.value);
        this.loadData();
    }

    onOpenRelevantInvoicesClick = () => {
        this.actionService.doAction("werlen_repuestos_erp.action_open_relevant_accountant_sale_fulfillment_order_list_view");
    };

    onColumnClick = (col) => {
        const context = {};

        if (col.key === "sent") {
            context.search_default_sent = true;
            context.search_default_avoid_tracking = true;
        } else {
            context[`search_default_${col.key}`] = true;
        }

        this.actionService.doAction(
            "werlen_repuestos_erp.action_open_relevant_accountant_sale_fulfillment_order_list_view",
            {
                additionalContext: context,
            }
        );

    };

    onOpenRelevantCreditNotesClick = () => {
        this.actionService.doAction("werlen_repuestos_erp.action_open_pending_reconciliation_credit_notes_out");
    };

    onOpenRelevantAccountPaymentsClick = () => {
        this.actionService.doAction("werlen_repuestos_erp.action_open_relevant_account_payment_list_view");
    };

    async onManualInPaymentClick() {
        if (!this.state.selectedJournalId) return;

        const action = await this.orm.call(
            "journal",
            "action_manual_in_payment",
            [[this.state.selectedJournalId]]
        );

        this.actionService.doAction(action, {
            onClose: () => this.loadData(),
        });
    }

    async onManualOutPaymentClick() {
        if (!this.state.selectedJournalId) return;

        const action = await this.orm.call(
            "journal",
            "action_manual_out_payment",
            [[this.state.selectedJournalId]]
        );

        this.actionService.doAction(action, {
            onClose: () => this.loadData(),
        });
    }

    async onOpenCreateCashSessionClick() {
        if (!this.state.selectedJournalId) return;

        const action = await this.orm.call(
            "journal",
            "action_create_cash_session",
            [[this.state.selectedJournalId]]
        );

        this.actionService.doAction(action, {
            onClose: () => this.loadData(),
        });
    }
}

AccountantDashboard.template = "werlen_repuestos_erp.AccountantDashboard";

registry.category("actions").add(
    "werlen_repuestos_erp.accountant_dashboard",
    AccountantDashboard
);
