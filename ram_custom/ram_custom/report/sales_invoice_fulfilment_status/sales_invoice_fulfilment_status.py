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
		{"label": _("Sales Invoice"), "fieldname": "sales_invoice", "fieldtype": "Link",
			"options": "Sales Invoice", "width": 160},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Is Return"), "fieldname": "is_return", "fieldtype": "Data", "width": 80},
		{"label": _("Update Stock"), "fieldname": "update_stock", "fieldtype": "Data", "width": 90},
		{"label": _("Linked Deliveries"), "fieldname": "linked_deliveries", "fieldtype": "Data", "width": 180},
		{"label": _("Linked Delivery Returns"), "fieldname": "linked_delivery_returns", "fieldtype": "Data", "width": 180},
		{"label": _("Invoice Amount"), "fieldname": "invoice_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Delivered Amount"), "fieldname": "delivered_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Returned Amount"), "fieldname": "returned_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Net Delivered"), "fieldname": "net_delivered", "fieldtype": "Currency", "width": 120},
		{"label": _("Remaining to Deliver"), "fieldname": "remaining_to_deliver", "fieldtype": "Currency", "width": 130},
		{"label": _("Fulfilment Status"), "fieldname": "fulfilment_status", "fieldtype": "Data", "width": 190},
	]


def get_data(filters):
	invoices = get_invoices(filters)
	if not invoices:
		return []

	invoice_names = [d.name for d in invoices]

	delivered_map, delivered_list_map = get_delivery_aggregate(invoice_names, is_return=0)
	returned_map, returned_list_map = get_delivery_aggregate(invoice_names, is_return=1)
	credit_note_map = get_credit_notes_by_original(invoice_names)

	rows = []
	show_returns = filters.get("show_returns") or "Both"

	for inv in invoices:
		is_return = 1 if inv.is_return else 0

		if show_returns == "Yes" and not is_return:
			continue
		if show_returns == "No" and is_return:
			continue

		invoice_amount = flt(inv.base_grand_total)
		delivered_amount = flt(delivered_map.get(inv.name))
		returned_amount = flt(returned_map.get(inv.name))
		net_delivered = delivered_amount - returned_amount
		remaining_to_deliver = invoice_amount - net_delivered

		status = compute_status(
			update_stock=inv.update_stock,
			is_return=is_return,
			invoice_name=inv.name,
			invoice_amount=invoice_amount,
			net_delivered=net_delivered,
			returned_amount=returned_amount,
			credit_note_map=credit_note_map,
		)

		if filters.get("fulfilment_status") and status != filters.get("fulfilment_status"):
			continue

		rows.append({
			"sales_invoice": inv.name,
			"posting_date": inv.posting_date,
			"company": inv.company,
			"customer": inv.customer,
			"is_return": "Yes" if is_return else "No",
			"update_stock": "Yes" if inv.update_stock else "No",
			"linked_deliveries": ", ".join(delivered_list_map.get(inv.name, [])),
			"linked_delivery_returns": ", ".join(returned_list_map.get(inv.name, [])),
			"invoice_amount": invoice_amount,
			"delivered_amount": delivered_amount,
			"returned_amount": returned_amount,
			"net_delivered": net_delivered,
			"remaining_to_deliver": remaining_to_deliver,
			"fulfilment_status": status,
		})

	return rows


def get_invoices(filters):
	conditions = ["si.docstatus = 1"]
	values = {}

	if filters.get("company"):
		conditions.append("si.company = %(company)s")
		values["company"] = filters["company"]

	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters["customer"]

	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	query = f"""
		SELECT
			si.name, si.posting_date, si.company, si.customer,
			si.is_return, si.update_stock, si.base_grand_total, si.return_against
		FROM `tabSales Invoice` si
		WHERE {" AND ".join(conditions)}
		ORDER BY si.posting_date DESC, si.name DESC
	"""
	return frappe.db.sql(query, values, as_dict=True)


def get_delivery_aggregate(invoice_names, is_return):
	if not invoice_names:
		return {}, {}

	rows = frappe.db.sql("""
		SELECT
			dni.against_sales_invoice AS invoice,
			dn.name AS delivery,
			SUM(dni.base_amount) AS amount
		FROM `tabDelivery Note Item` dni
		INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
		WHERE dn.docstatus = 1
			AND dn.is_return = %(is_return)s
			AND dni.against_sales_invoice IN %(invoices)s
		GROUP BY dni.against_sales_invoice, dn.name
	""", {"is_return": is_return, "invoices": invoice_names}, as_dict=True)

	amount_map = {}
	list_map = {}
	for r in rows:
		amount_map[r.invoice] = amount_map.get(r.invoice, 0) + abs(flt(r.amount))
		list_map.setdefault(r.invoice, []).append(r.delivery)

	return amount_map, list_map


def get_credit_notes_by_original(invoice_names):
	if not invoice_names:
		return {}

	rows = frappe.db.sql("""
		SELECT return_against
		FROM `tabSales Invoice`
		WHERE docstatus = 1
			AND is_return = 1
			AND return_against IN %(invoices)s
	""", {"invoices": invoice_names}, as_dict=True)

	return {r.return_against: True for r in rows}


def compute_status(update_stock, is_return, invoice_name, invoice_amount,
					net_delivered, returned_amount, credit_note_map):
	if update_stock:
		return "Stock Updated"

	if is_return:
		if returned_amount > 0:
			return "Fully Reversed"
		return "Return Unmatched"

	has_delivery_return = returned_amount > 0
	has_credit_note = credit_note_map.get(invoice_name, False)

	if has_delivery_return and not has_credit_note:
		return "Delivery Returned, Invoice Open"

	if has_delivery_return and has_credit_note:
		if abs(invoice_amount - net_delivered) > 0.01:
			return "Partially Reversed"
		return "Fully Reversed"

	if net_delivered <= 0:
		return "Not Delivered"
	if net_delivered < invoice_amount:
		return "Partially Delivered"
	return "Fully Delivered"
