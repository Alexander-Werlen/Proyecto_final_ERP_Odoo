/** @odoo-module **/

import { Component, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class ReceptionDashboard extends Component {

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
            "reception",
            "get_reception_dashboard_data",
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

    onCreateReceptionClick = () => {
        this.actionService.doAction("werlen_repuestos_erp.action_create_reception");
    };

    onOpenAllClick = () => {
        this.actionService.doAction("werlen_repuestos_erp.action_open_receptions");
    };

    onColumnClick = (col) => {
        const context = {
            [`search_default_${col.key}`]: 1,
        };

        this.actionService.doAction(
            "werlen_repuestos_erp.action_open_receptions",
            {
                additionalContext: context,
            }
        );
    };

}

ReceptionDashboard.template =
    "werlen_repuestos_erp.ReceptionDashboard";

registry.category("actions").add(
    "werlen_repuestos_erp.reception_dashboard",
    ReceptionDashboard
);
