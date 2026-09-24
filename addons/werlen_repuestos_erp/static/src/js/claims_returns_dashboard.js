/** @odoo-module **/

import { Component, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class ClaimsReturnsDashboard extends Component {

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.state = useState({
            userName: session.partner_display_name || "",
            suppliers: [],
            loading: true,
            isFirstLoad: false,
            hasAnyActivity: true,
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
            "supplier_claim",
            "get_claims_returns_dashboard_data",
            []
        );

        this.state.suppliers = (result.suppliers || []).map((supplier) => ({
            ...supplier,
            open_claims_total: supplier._open_claims_total,
            in_progress_claims_total: supplier._in_progress_claims_total,
            returns_total: supplier._returns_total,
        }));
        this.state.hasAnyActivity = this.state.suppliers.length > 0;
        this.state.loading = false;

        const isFirst = !this._hasLoaded;
        this._hasLoaded = true;

        if (isFirst) {
            this.state.isFirstLoad = true;
            setTimeout(() => {
                this.state.isFirstLoad = false;
            }, 600);
        }
    }

    onSupplierClick(supplier) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: supplier.name,
            res_model: "res.partner",
            res_id: supplier.id,
            view_mode: "form",
            views: [[false, "form"]],
        });
    }

    onSectionClick(supplier, stateKey) {
        if (stateKey === "returns") {
            this.actionService.doAction({
                type: "ir.actions.act_window",
                name: "Devoluciones - " + supplier.name,
                res_model: "return_note",
                view_mode: "list,form",
                domain: [
                    ["supplier_id", "=", supplier.id],
                    ["state", "in", ["draft", "prepared", "sent"]],
                ],
                views: [[false, "list"], [false, "form"]],
            });
        } else {
            this.actionService.doAction({
                type: "ir.actions.act_window",
                name: "Reclamos - " + supplier.name,
                res_model: "supplier_claim",
                view_mode: "list,form",
                domain: [
                    ["supplier_id", "=", supplier.id],
                    ["state", "=", stateKey],
                ],
                views: [[false, "list"], [false, "form"]],
            });
        }
    }

    onClaimTypeClick(supplier, typeGroup, stateKey) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: typeGroup.claim_type_label + " - " + supplier.name,
            res_model: "supplier_claim",
            view_mode: "list,form",
            domain: [
                ["supplier_id", "=", supplier.id],
                ["state", "=", stateKey],
                ["claim_type", "=", typeGroup.claim_type],
            ],
            views: [[false, "list"], [false, "form"]],
        });
    }

    onProductClick(supplier, product, claimType, stateKey) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: product.code + " - " + product.name,
            res_model: "supplier_claim",
            view_mode: "list,form",
            domain: [
                ["supplier_id", "=", supplier.id],
                ["state", "=", stateKey],
                ["claim_type", "=", claimType],
                ["product_id", "=", product.id],
            ],
            views: [[false, "list"], [false, "form"]],
        });
    }

    onReturnClick(returnNote) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: returnNote.name,
            res_model: "return_note",
            res_id: returnNote.id,
            view_mode: "form",
            views: [[false, "form"]],
        });
    }

}

ClaimsReturnsDashboard.template = "werlen_repuestos_erp.ClaimsReturnsDashboard";

registry.category("actions").add(
    "werlen_repuestos_erp.claims_returns_dashboard",
    ClaimsReturnsDashboard
);

