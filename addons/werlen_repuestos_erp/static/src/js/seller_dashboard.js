/** @odoo-module **/

import { Component, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class SellerDashboard extends Component {

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.state = useState({
            columns: [],
            userName: session.partner_display_name || "",
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
            "get_seller_dashboard_data",
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

    onOpenRelevantInvoicesClick = () => {
        this.actionService.doAction("werlen_repuestos_erp.action_open_relevant_seller_sale_fulfillment_order");
    };

    onCreateInvoiceClick = () => {
        this.actionService.doAction("werlen_repuestos_erp.action_invoice_out_create_wizard");
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
            "werlen_repuestos_erp.action_open_issued_by_self_seller_sale_fulfillment_order",
            {
                additionalContext: context,
            }
        );

    };
}

SellerDashboard.template = "werlen_repuestos_erp.SellerDashboard";

registry.category("actions").add(
    "werlen_repuestos_erp.seller_dashboard",
    SellerDashboard
);
