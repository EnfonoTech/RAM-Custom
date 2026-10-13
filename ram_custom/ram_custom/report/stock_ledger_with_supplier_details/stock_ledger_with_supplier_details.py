# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""Stock Ledger with Supplier, Supplier Invoice No and Supplier Invoice Date.

The standard ERPNext Stock Ledger is run untouched; this report only adds three
columns right after "Voucher #". Because the columns are part of the report
itself, the layout is the same for every user and every visit - nothing to
re-arrange per user.

Where the three values come from (looked up in bulk, one query per document
type, never one query per row):

* Purchase Invoice  - supplier, bill_no, bill_date on the invoice itself.
* Purchase Receipt  - the "Supplier Invoice No / Date" typed on the receipt
  itself. If that is empty, the supplier invoice that later billed this receipt
  (through Purchase Invoice Item.purchase_receipt). If neither exists, the
  supplier's own delivery note number is shown and the date is left empty.
* Any other voucher (Delivery Note, Stock Entry, ...) - left empty.
"""

from collections import defaultdict

import frappe
from erpnext.stock.report.stock_ledger.stock_ledger import execute as stock_ledger_execute
from frappe import _

CHUNK = 1000


def execute(filters=None):
	result = stock_ledger_execute(filters)
	columns, data = result[0], result[1]

	insert_supplier_columns(columns)
	add_supplier_details(data)

	return (columns, data, *result[2:])


def insert_supplier_columns(columns):
	new_columns = [
		{
			"label": _("Supplier"),
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 160,
		},
		{
			"label": _("Supplier Invoice No"),
			"fieldname": "supplier_invoice_no",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Supplier Invoice Date"),
			"fieldname": "supplier_invoice_date",
			"fieldtype": "Date",
			"width": 120,
		},
	]

	position = next(
		(idx + 1 for idx, col in enumerate(columns) if col.get("fieldname") == "voucher_no"),
		len(columns),
	)
	columns[position:position] = new_columns


def add_supplier_details(data):
	vouchers = defaultdict(set)
	for row in data:
		voucher_type, voucher_no = row.get("voucher_type"), row.get("voucher_no")
		if voucher_type in ("Purchase Invoice", "Purchase Receipt") and voucher_no:
			vouchers[voucher_type].add(voucher_no)

	if not vouchers:
		return

	invoices = get_purchase_invoice_details(vouchers.get("Purchase Invoice", ()))
	receipts = get_purchase_receipt_details(vouchers.get("Purchase Receipt", ()))

	for row in data:
		details = None
		if row.get("voucher_type") == "Purchase Invoice":
			details = invoices.get(row.get("voucher_no"))
		elif row.get("voucher_type") == "Purchase Receipt":
			details = receipts.get(row.get("voucher_no"))

		if details:
			row.update(details)


def get_purchase_invoice_details(names):
	out = {}
	pi = frappe.qb.DocType("Purchase Invoice")
	for batch in _chunks(names):
		rows = (
			frappe.qb.from_(pi)
			.select(pi.name, pi.supplier, pi.bill_no, pi.bill_date)
			.where(pi.name.isin(batch))
		).run(as_dict=True)
		for r in rows:
			out[r.name] = {
				"supplier": r.supplier,
				"supplier_invoice_no": r.bill_no,
				"supplier_invoice_date": r.bill_date,
			}
	return out


def get_purchase_receipt_details(names):
	out = {}
	meta = frappe.get_meta("Purchase Receipt")
	number_field = "custom_supplier_invoice_number"
	date_field = "custom_supplier_invoice_date"
	has_receipt_invoice = meta.has_field(number_field) and meta.has_field(date_field)

	pr = frappe.qb.DocType("Purchase Receipt")
	fields = [pr.name, pr.supplier, pr.supplier_delivery_note]
	if has_receipt_invoice:
		fields += [pr[number_field], pr[date_field]]

	for batch in _chunks(names):
		for r in frappe.qb.from_(pr).select(*fields).where(pr.name.isin(batch)).run(as_dict=True):
			invoice_no = r.get(number_field) if has_receipt_invoice else None
			out[r.name] = {
				"supplier": r.supplier,
				"supplier_invoice_no": invoice_no or r.supplier_delivery_note,
				"supplier_invoice_date": r.get(date_field) if invoice_no else None,
				"_from_receipt": bool(invoice_no),
			}

	# Receipts with no invoice number typed on them: use the invoice that billed them.
	missing = [name for name, d in out.items() if not d.pop("_from_receipt")]
	pii = frappe.qb.DocType("Purchase Invoice Item")
	pi = frappe.qb.DocType("Purchase Invoice")
	for batch in _chunks(missing):
		billed = (
			frappe.qb.from_(pii)
			.join(pi)
			.on(pi.name == pii.parent)
			.select(pii.purchase_receipt, pi.bill_no, pi.bill_date)
			.where(pii.purchase_receipt.isin(batch) & (pi.docstatus == 1) & (pi.bill_no != ""))
			.orderby(pi.posting_date)
			.orderby(pi.name)
		).run(as_dict=True)
		seen = set()
		for r in billed:
			if r.purchase_receipt in seen:
				continue
			seen.add(r.purchase_receipt)
			out[r.purchase_receipt].update(
				{"supplier_invoice_no": r.bill_no, "supplier_invoice_date": r.bill_date}
			)
	return out


def _chunks(names):
	names = sorted(names)
	for i in range(0, len(names), CHUNK):
		yield names[i : i + CHUNK]
