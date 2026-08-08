/** @odoo-module **/

import { Component, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class PreparationTeamDashboard extends Component {

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.state = useState({
            columns: [],
            maxBoxes: 12,
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
            "get_preparation_team_dashboard_data",
            []
        );

        this.state.maxBoxes = result.max_boxes;

        this.state.columns = result.columns.map(col => {
            const boxes = Math.min(col.count, this.state.maxBoxes);
            const empty = this.state.maxBoxes - boxes;
            const overflow = Math.max(0, col.count - this.state.maxBoxes);

            return {
                ...col,
                boxes,
                empty,
                overflow,
            };
        });

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
        this.actionService.doAction(
            "werlen_repuestos_erp.action_open_relevant_preparation_sale_fulfillment_order_list_view"
        );
    };

    onColumnClick = (col) => {
        const context = {
            group_by: "who_withdraws",
            group_by_no_leaf: true,
        };

        if (col.key === "sent") {
            context.search_default_today_sent = true;
        } else {
            context[`search_default_${col.key}`] = true;
        }

        this.actionService.doAction(
            "werlen_repuestos_erp.action_open_preparation_sale_fulfillment_order_list_view",
            {
                additionalContext: context,
            }
        );
        
    };

}

PreparationTeamDashboard.template =
    "werlen_repuestos_erp.PreparationTeamDashboard";

registry.category("actions").add(
    "werlen_repuestos_erp.preparation_team_dashboard",
    PreparationTeamDashboard
);
