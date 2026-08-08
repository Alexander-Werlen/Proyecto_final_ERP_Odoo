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

    animateValue(obj, key, start, end, duration = 600) {
        if (start === end) {
            obj[key] = end;
            return;
        }
        const range = end - start;
        const startTime = performance.now();
        const step = (now) => {
            const progress = Math.min((now - startTime) / duration, 1);
            const ease = 1 - Math.pow(1 - progress, 3);
            obj[key] = Math.round(start + range * ease);
            if (progress < 1) {
                requestAnimationFrame(step);
            } else {
                obj[key] = end;
            }
        };
        requestAnimationFrame(step);
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

        const max = Math.max(1, ...result.columns.map(col => col.count));

        result.columns.forEach(col => {
            col.height = col.count ? Math.max(6, (col.count / max) * 100) : 0;
        });

        this.state.columns = result.columns;

        this.state.loading = false;

        const isFirst = !this._hasLoaded;
        this._hasLoaded = true;

        if (isFirst) {
            this.state.isFirstLoad = true;
            this.state.columns.forEach((col) => {
                col.displayTotal = 0;
                this.animateValue(col, "displayTotal", 0, col.count, 1200);
            });
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
            context.search_default_today_sent = true;
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
