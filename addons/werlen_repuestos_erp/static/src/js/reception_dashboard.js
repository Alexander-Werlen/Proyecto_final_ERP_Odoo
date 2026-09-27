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
            preparedReturnNotesCount: 0,
            canCreateReception: false,
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
            "reception",
            "get_reception_dashboard_data",
            []
        );

        this.state.maxBoxes = result.max_boxes;
        this.state.preparedReturnNotesCount =
            result.prepared_return_notes_count || 0;
        this.state.canCreateReception =
            result.can_create_reception || false;

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

    onPreparedReturnsClick = () => {
        this.actionService.doAction(
            "werlen_repuestos_erp.action_open_return_notes",
            {
                additionalContext: {
                    search_default_prepared: 1,
                    search_default_group_supplier: 1,
                },
            }
        );
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
