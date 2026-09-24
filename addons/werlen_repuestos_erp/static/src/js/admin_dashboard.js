/** @odoo-module **/

import { Component, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class AdminDashboard extends Component {

    setup() {

        this.orm = useService("orm");
        this.actionService = useService("action");

        this.state = useState({
            userName: session.partner_display_name || "",
            models: [],
            layoutGroups: [],
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

        const result = await this.orm.call(
            "sale_fulfillment_order",
            "get_admin_dashboard_data",
            []
        );

        this.state.models = result.models || [];
        const modelsByKey = Object.fromEntries(
            this.state.models.map((model) => [model.key, model])
        );
        this.state.layoutGroups = [
            {
                key: "sales",
                models: [modelsByKey.sale_fulfillment_order],
            },
            {
                key: "credit-notes",
                models: [modelsByKey.credit_note_out],
            },
            {
                key: "supplier-claims",
                models: [modelsByKey.supplier_claim],
            },
            {
                key: "client-claims",
                models: [modelsByKey.client_claim],
            },
            {
                key: "receipts",
                models: [modelsByKey.account_payment],
            },
            {
                key: "movements",
                models: [modelsByKey.movements],
            },
        ].map((group) => ({
            ...group,
            models: group.models.filter(Boolean),
        })).filter((group) => group.models.length);

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

    onIssueClick = (issue) => {
        if (issue.action) {
            this.actionService.doAction(issue.action);
        }
    };

}

AdminDashboard.template = "werlen_repuestos_erp.AdminDashboard";

registry.category("actions").add(
    "werlen_repuestos_erp.admin_dashboard",
    AdminDashboard
);
