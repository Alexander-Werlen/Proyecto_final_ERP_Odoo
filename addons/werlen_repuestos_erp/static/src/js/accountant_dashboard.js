/** @odoo-module **/

import { Component, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class AccountantDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            columns: [],
            creditNotes: 0,
            userName: session.partner_display_name || "",
            loading: true,
        });
        this.loadData();
        this.interval = setInterval(() => this.loadData(), 10000);
        onWillUnmount(() => clearInterval(this.interval));
    }

    async loadData() {
        const result = await this.orm.call(
            "sale_fulfillment_order",
            "get_accountant_dashboard_data",
            []
        );
        this.state.columns = result.columns || [];
        this.state.creditNotes = result.unreconciled_credit_notes_count || 0;
        this.state.loading = false;
    }

    onColumnClick = (column) => {
        this.actionService.doAction(
            "werlen_repuestos_erp.action_open_relevant_accountant_sale_fulfillment_order_list_view",
            { additionalContext: { [`search_default_${column.key}`]: 1 } }
        );
    };

    onCreditNotesClick = () => {
        this.actionService.doAction("werlen_repuestos_erp.action_open_credit_notes_out");
    };
}

AccountantDashboard.template = "werlen_repuestos_erp.AccountantDashboard";
registry.category("actions").add(
    "werlen_repuestos_erp.accountant_dashboard",
    AccountantDashboard
);
