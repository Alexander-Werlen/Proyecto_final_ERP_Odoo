import csv
import logging
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from odoo import api, models

from .utils.custom_string_match import match_city, match_province


_logger = logging.getLogger(__name__)
BUENOS_AIRES_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
UTC_TZ = ZoneInfo("UTC")


class UnsupportedVoucherError(ValueError):
    """Raised when a CSV row belongs to a not-yet-implemented voucher type."""


class SyncInvoices(models.Model):
    _name = "sync_invoices"
    _description = "Importación de comprobantes externos"

    @api.model
    def import_file(self, path, correlation_id=None):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No existe el archivo a importar: {path}")

        _logger.info("[%s] importing file %s", correlation_id or "-", path)
        processed_rows = 0

        with open(path, newline="", encoding="latin-1") as csv_file:
            reader = csv.DictReader(csv_file, delimiter=";")
            if not reader.fieldnames:
                raise ValueError(f"El archivo {path} no tiene cabecera CSV.")

            fieldnames = {self._clean_key(fieldname) for fieldname in reader.fieldnames}
            for raw_row in reader:
                row = {
                    self._clean_key(key): value
                    for key, value in raw_row.items()
                    if key is not None
                }
                if not any(self._clean_value(value) for value in row.values()):
                    continue

                voucher = self._clean_value(row.get("Comprobante")).upper()
                if voucher == "FC":
                    self._process_invoice_out_line(row, os.path.basename(path))
                elif voucher in {"NC", "ND"}:
                    self._process_credit_note_out_line(row, os.path.basename(path))
                elif voucher in {"RC", "RECIBO"} or "Descuentos" in fieldnames:
                    self._process_account_payment_line(row, os.path.basename(path))
                else:
                    raise UnsupportedVoucherError(
                        f"El archivo {path} contiene un comprobante no soportado: "
                        f"{voucher or 'sin tipo'}."
                    )

                processed_rows += 1

        if not processed_rows:
            raise ValueError(f"El archivo {path} no contiene comprobantes.")

    def _process_invoice_out_line(self, row, csv_file):
        invoice_type_code = self._required(row, "Comprobante", csv_file).upper()
        letter = self._required(row, "Letra", csv_file).upper()
        if invoice_type_code != "FC":
            raise ValueError(f"Tipo de factura inválido en {csv_file}: {invoice_type_code}")

        invoice_type_name = f"{invoice_type_code}-{letter}"
        invoice_number = self._required(row, "Numero", csv_file)
        invoice_id = f"{invoice_type_name}-{invoice_number}"

        invoice_type = self.env["invoice_type"].sudo().search(
            [("invoice_type_id", "=", invoice_type_name)],
            limit=1,
        )
        if not invoice_type:
            raise ValueError(
                f"La factura {csv_file} tiene un tipo desconocido: {invoice_type_name}."
            )

        company = self.env["res.company"].sudo().search([], limit=1)
        if not company:
            raise ValueError("No existe una compañía configurada en Odoo.")
        if self.env["invoice_out"].sudo().search(
            [
                ("invoice_id", "=", invoice_id),
                ("invoice_type", "=", invoice_type.id),
                ("company_id", "=", company.id),
            ],
            limit=1,
        ):
            raise ValueError(f"Ya existe una factura con identificador {invoice_id}.")

        client_identifier = "C" + self._required(row, "Cuenta", csv_file)
        full_name = self._clean_value(row.get("Apellido y nombre"))
        client = self._find_or_create_client(client_identifier, full_name)

        state_name = match_province(self._clean_value(row.get("Provincia")))
        state = self._find_state(state_name)
        zip_code = self._clean_value(row.get("CodPostal"))
        city_name = match_city(
            self._clean_value(row.get("Localidad")),
            self.env["city"].sudo().search([]).mapped("name"),
        )
        city = self._find_or_create_city(city_name, state, zip_code, csv_file)

        seller_identifier = "E" + self._required(row, "Vendedor", csv_file)
        seller = self._find_or_create_seller(seller_identifier)

        payment_method_name = self._clean_value(row.get("Cond.Venta")) or "OTROS"
        payment_method = self._find_or_create_payment_method(payment_method_name)

        point_of_sale = self.env["point_of_sale"].sudo().search(
            [("name", "=", "Mostrador")],
            limit=1,
        )
        if not point_of_sale:
            raise ValueError("No existe el punto de venta 'Mostrador'.")

        values = {
            "invoice_id": invoice_id,
            "invoice_type": invoice_type.id,
            "company_id": company.id,
            "client": client.id,
            "full_name": full_name or client.name,
            "total_cost": float(self._parse_money(row.get("Importe"), "Importe", csv_file)),
            "city": city.id if city else False,
            "zip_code": zip_code or False,
            "state": state.id if state else False,
            "destination": self._clean_value(row.get("Direccion")),
            "seller": seller.id,
            "payment_method": payment_method.id,
            "point_of_sale": point_of_sale.id,
            "is_draft": False,
            "is_manual_invoice": False,
        }

        parsed_date = self._parse_datetime(row, csv_file)
        if parsed_date:
            values["date"] = parsed_date

        invoice = self.env["invoice_out"].sudo().create(values)
        self.env["sale_fulfillment_order"].sudo().create(
            {
                "sale_fulfillment_order_id": invoice_id,
                "invoice_id": invoice.id,
                "point_of_sale": point_of_sale.id,
                "city": city.id if city else False,
                "zip_code": zip_code or False,
                "state": state.id if state else False,
                "destination": values["destination"],
                "logistical_status": "draft",
            }
        )
        _logger.info("Created invoice %s from %s", invoice_id, csv_file)

    def _process_credit_note_out_line(self, row, csv_file):
        voucher = self._clean_value(row.get("Comprobante")).upper() or "NC/ND"
        raise UnsupportedVoucherError(
            f"La importación de {voucher} todavía no está implementada ({csv_file})."
        )

    def _process_account_payment_line(self, row, csv_file):
        raise UnsupportedVoucherError(
            f"La importación de recibos todavía no está implementada ({csv_file})."
        )

    def _find_state(self, state_name):
        if not state_name:
            return self.env["res.country.state"]

        argentina = self.env.ref("base.ar")
        return self.env["res.country.state"].sudo().search(
            [
                ("name", "ilike", state_name),
                ("country_id", "=", argentina.id),
            ],
            limit=1,
        )

    def _find_or_create_city(self, city_name, state, zip_code, csv_file):
        if not city_name:
            return self.env["city"]
        if not zip_code:
            raise ValueError(f"La factura {csv_file} no tiene código postal para la ciudad.")

        domain = [("name", "=", city_name), ("zip_code", "=", zip_code)]
        if state:
            domain.append(("state_id", "=", state.id))
        else:
            domain.append(("state_id", "=", False))

        city_model = self.env["city"].sudo()
        city = city_model.search(domain, limit=1)
        if city:
            return city

        return city_model.create(
            {
                "name": city_name,
                "state_id": state.id if state else False,
                "zip_code": zip_code,
            }
        )

    def _find_or_create_client(self, identifier, full_name):
        partner_model = self.env["res.partner"].sudo()
        client = partner_model.search(
            [("unique_identifier", "=", identifier)],
            limit=1,
        )
        if client:
            return client

        name = full_name or "Falta definir"
        return partner_model.create(
            {
                "unique_identifier": identifier,
                "name": f"{name} ({identifier})",
            }
        )

    def _find_or_create_seller(self, identifier):
        user_model = self.env["res.users"].sudo()
        seller = user_model.search(
            [("partner_id.unique_identifier", "=", identifier)],
            limit=1,
        )
        if seller:
            return seller

        partner = self.env["res.partner"].sudo().create(
            {
                "unique_identifier": identifier,
                "name": f"Falta definir ({identifier})",
                "email": identifier,
            }
        )
        return user_model.create(
            {
                "name": f"Falta definir ({identifier})",
                "login": identifier,
                "partner_id": partner.id,
                "company_id": self.env["res.company"].sudo().search([], limit=1).id,
                "notification_type": "inbox",
            }
        )

    def _find_or_create_payment_method(self, name):
        payment_model = self.env["payment_method"].sudo()
        payment_method = payment_model.search([("name", "=", name)], limit=1)
        if payment_method:
            return payment_method
        return payment_model.create({"name": name, "active_currently": False})

    @staticmethod
    def _clean_key(value):
        return str(value or "").replace("\ufeff", "").replace("ï»¿", "").strip()

    @staticmethod
    def _clean_value(value):
        return str(value or "").replace("\x00", "").strip()

    def _required(self, row, field_name, csv_file):
        value = self._clean_value(row.get(field_name))
        if not value:
            raise ValueError(f"La factura {csv_file} no tiene el campo {field_name}.")
        return value

    def _parse_money(self, value, field_name, csv_file):
        raw_value = self._clean_value(value)
        if not raw_value:
            raise ValueError(f"La factura {csv_file} no tiene el importe {field_name}.")

        try:
            return Decimal(raw_value.replace(".", "").replace(",", "."))
        except InvalidOperation as error:
            raise ValueError(
                f"El importe {field_name} de {csv_file} no es válido: {raw_value}."
            ) from error

    def _parse_datetime(self, row, csv_file):
        raw_date = self._clean_value(row.get("Fecha"))
        raw_hour = self._clean_value(row.get("Hora"))
        if not raw_date:
            return None

        try:
            if raw_hour:
                parsed = datetime.strptime(
                    raw_date + raw_hour.replace(":", ""),
                    "%Y%m%d%H%M",
                )
            else:
                parsed = datetime.strptime(raw_date, "%Y%m%d")
        except ValueError as error:
            raise ValueError(
                f"La fecha/hora de {csv_file} no es válida: {raw_date} {raw_hour}."
            ) from error

        return parsed.replace(tzinfo=BUENOS_AIRES_TZ).astimezone(UTC_TZ).replace(tzinfo=None)
