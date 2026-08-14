import logging
import os
from pathlib import Path
import uuid

from odoo import SUPERUSER_ID, fields, http
from odoo.http import request


_logger = logging.getLogger(__name__)


class LegacyInvoiceController(http.Controller):
    @http.route(
        "/legacy/invoice/import",
        type="json",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def import_invoice(
        self,
        api_key=None,
        filename=None,
        path=None,
        attempt=1,
        correlation_id=None,
    ):
        if not self._check_api_key(api_key):
            return {"status": "failed", "reason": "invalid_api_key"}

        safe_path = self._safe_processing_path(path)
        if safe_path is None or not safe_path.is_file():
            return {"status": "failed", "reason": "file_not_found"}

        try:
            attempt = max(1, int(attempt))
        except (TypeError, ValueError):
            return {"status": "failed", "reason": "invalid_attempt"}

        correlation_id = correlation_id or str(uuid.uuid4())
        filename = os.path.basename(filename or safe_path.name)
        company = request.env["res.company"].sudo().search([], limit=1)
        if not company:
            return {"status": "failed", "reason": "company_not_found"}

        import_model = (
            request.env["legacy_invoice_import"]
            .with_user(SUPERUSER_ID)
            .sudo()
            .with_company(company)
        )
        record = import_model.search(
            [("correlation_id", "=", correlation_id)],
            limit=1,
        )

        if not record:
            record = import_model.create(
                {
                    "filename": filename,
                    "path": str(safe_path),
                    "correlation_id": correlation_id,
                }
            )
        elif record.state == "done":
            return {"status": "ok", "already_processed": True}

        record.write(
            {
                "state": "processing",
                "attempts": attempt,
                "last_attempt_at": fields.Datetime.now(),
                "last_error": False,
            }
        )

        try:
            with request.env.cr.savepoint():
                (
                    request.env["sync_invoices"]
                    .with_user(SUPERUSER_ID)
                    .sudo()
                    .with_company(company)
                    .import_file(str(safe_path), correlation_id)
                )

            record.write({"state": "done", "last_error": False})
            return {"status": "ok"}
        except Exception as error:
            _logger.exception("[%s] import error", correlation_id)
            state = "retry" if attempt < 3 else "failed"
            record.write({"state": state, "last_error": str(error)})

            if state == "retry":
                return {
                    "status": "retry",
                    "reason": str(error),
                    "retry_after": 60 * attempt,
                }
            return {"status": "failed", "reason": str(error)}

    @staticmethod
    def _safe_processing_path(path):
        if not path:
            return None

        processing_dir = Path(
            os.environ.get("LEGACY_INVOICE_PROCESSING_DIR", "/app/data/facturas/processing")
        ).resolve()
        candidate = Path(path).resolve()
        try:
            candidate.relative_to(processing_dir)
        except ValueError:
            _logger.warning("Rejected legacy import path outside processing directory: %s", path)
            return None
        return candidate

    @staticmethod
    def _check_api_key(api_key):
        configured_key = os.environ.get("ODOO_API_KEY")
        if not configured_key:
            configured_key = request.env["ir.config_parameter"].sudo().get_param(
                "werlen_repuestos_erp.legacy_api_key"
            )
        return bool(api_key and configured_key and api_key == configured_key)
