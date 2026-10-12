# Copyright (c) 2026, ramees and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Purchase Invoice"), "fieldname": "purchase_invoice", "fieldtype": "Link",
			"options": "Purchase Invoice", "width": 160},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Is Return"), "fieldname": "is_return", "fieldtype": "Data", "width": 80},
		{"label": _("Update Stock"), "fieldname": "update_stock", "fieldtype": "Data", "width": 90},
		{"label": _("Linked Receipts"), "fieldname": "linked_receipts", "fieldtype": "Data", "width": 180},
		{"label": _("Linked Receipt Returns"), "fieldname": "linked_receipt_returns", "fieldtype": "Data", "width": 180},
		{"label": _("Invoice Amount"), "fieldname": "invoice_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Received Amount"), "fieldname": "received_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Returned Amount"), "fieldname": "returned_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Net Received"), "fieldname": "net_received", "fieldtype": "Currency", "width": 120},
		{"label": _("Remaining to Receive"), "fieldname": "remaining_to_receive", "fieldtype": "Currency", "width": 130},
		{"label": _("Fulfilment Status"), "fieldname": "fulfilment_status", "fieldtype": "Data", "width": 190},
	]


def get_data(filters):
	invoices = get_invoices(filters)
	if not invoices:
		return []

	invoice_names = [d.name for d in invoices]

	received_map, received_list_map = get_receipt_aggregate(invoice_names, is_return=0)
	returned_map, returned_list_map = get_receipt_aggregate(invoice_names, is_return=1)
	debit_note_map = get_debit_notes_by_original(invoice_names)

	rows = []
	show_returns = filters.get("show_returns") or "Both"

	for inv in invoices:
		is_return = 1 if inv.is_return else 0

		if show_returns == "Yes" and not is_return:
			continue
		if show_returns == "No" and is_return:
			continue

		invoice_amount = flt(inv.base_grand_total)
		received_amount = flt(received_map.get(inv.name))
		returned_amount = flt(returned_map.get(inv.name))
		net_received = received_amount - returned_amount
		remaining_to_receive = invoice_amount - net_received

		status = compute_status(
			update_stock=inv.update_stock,
			is_return=is_return,
			invoice_name=inv.name,
			invoice_amount=invoice_amount,
			net_received=net_received,
			returned_amount=returned_amount,
			debit_note_map=debit_note_map,
		)

		if filters.get("fulfilment_status") and status != filters.get("fulfilment_status"):
			continue

		rows.append({
			"purchase_invoice": inv.name,
			"posting_date": inv.posting_date,
			"company": inv.company,
			"supplier": inv.supplier,
			"is_return": "Yes" if is_return else "No",
			"update_stock": "Yes" if inv.update_stock else "No",
			"linked_receipts": ", ".join(received_list_map.get(inv.name, [])),
			"linked_receipt_returns": ", ".join(returned_list_map.get(inv.name, [])),
			"invoice_amount": invoice_amount,
			"received_amount": received_amount,
			"returned_amount": returned_amount,
			"net_received": net_received,
			"remaining_to_receive": remaining_to_receive,
			"fulfilment_status": status,
		})

	return rows


def get_invoices(filters):
	conditions = ["pi.docstatus = 1"]
	values = {}

	if filters.get("company"):
		conditions.append("pi.company = %(company)s")
		values["company"] = filters["company"]

	if filters.get("supplier"):
		conditions.append("pi.supplier = %(supplier)s")
		values["supplier"] = filters["supplier"]

	if filters.get("from_date"):
		conditions.append("pi.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("pi.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	query = f"""
		SELECT
			pi.name, pi.posting_date, pi.company, pi.supplier,
			pi.is_return, pi.update_stock, pi.base_grand_total, pi.return_against
		FROM `tabPurchase Invoice` pi
		WHERE {" AND ".join(conditions)}
		ORDER BY pi.posting_date DESC, pi.name DESC
	"""
	return frappe.db.sql(query, values, as_dict=True)


def get_receipt_aggregate(invoice_names, is_return):
	if not invoice_names:
		return {}, {}

	rows = frappe.db.sql("""
		SELECT
			pri.purchase_invoice AS invoice,
			pr.name AS receipt,
			SUM(pri.base_amount) AS amount
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1
			AND pr.is_return = %(is_return)s
			AND pri.purchase_invoice IN %(invoices)s
		GROUP BY pri.purchase_invoice, pr.name
	""", {"is_return": is_return, "invoices": invoice_names}, as_dict=True)

	amount_map = {}
	list_map = {}
	for r in rows:
		amount_map[r.invoice] = amount_map.get(r.invoice, 0) + abs(flt(r.amount))
		list_map.setdefault(r.invoice, []).append(r.receipt)

	return amount_map, list_map


def get_debit_notes_by_original(invoice_names):
	if not invoice_names:
		return {}

	rows = frappe.db.sql("""
		SELECT return_against
		FROM `tabPurchase Invoice`
		WHERE docstatus = 1
			AND is_return = 1
			AND return_against IN %(invoices)s
	""", {"invoices": invoice_names}, as_dict=True)

	return {r.return_against: True for r in rows}


def compute_status(update_stock, is_return, invoice_name, invoice_amount,
					net_received, returned_amount, debit_note_map):
	if update_stock:
		return "Stock Updated"

	if is_return:
		if returned_amount > 0:
			return "Fully Reversed"
		return "Return Unmatched"

	has_receipt_return = returned_amount > 0
	has_debit_note = debit_note_map.get(invoice_name, False)

	if has_receipt_return and not has_debit_note:
		return "Receipt Returned, Invoice Open"

	if has_receipt_return and has_debit_note:
		if abs(invoice_amount - net_received) > 0.01:
			return "Partially Reversed"
		return "Fully Reversed"

	if net_received <= 0:
		return "Not Received"
	if net_received < invoice_amount:
		return "Partially Received"
	return "Fully Received"
