# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""Invoices Awaiting Receipt.

Rukn books many Purchase Invoices before the goods are received (Update Stock
off, no Purchase Order) and enters the Purchase Receipt later. ERPNext holds no
link between the two, so the standard "To Be Billed" / fulfilment views cannot
tell which invoices are still waiting for goods.

Both documents carry the supplier's invoice number (Purchase Invoice `bill_no`,
Purchase Receipt `custom_supplier_invoice_number`), so they are paired on

    supplier + supplier invoice number (case, spaces and dashes ignored)

A Purchase Invoice whose items point at a Purchase Receipt directly counts as
matched as well. Four views:

* Invoices Awaiting Receipt   - stock Purchase Invoice with no receipt
* Receipts Without Invoice    - Purchase Receipt with no invoice
* Amount Mismatch             - paired by number, totals differ
* Possible Duplicate Receipts - same supplier invoice entered twice
"""

import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, date_diff, flt, getdate, today

VIEW_AWAITING = "Invoices Awaiting Receipt"
VIEW_NO_INVOICE = "Receipts Without Invoice"
VIEW_MISMATCH = "Amount Mismatch"
VIEW_DUPLICATE = "Possible Duplicate Receipts"
VIEWS = (VIEW_AWAITING, VIEW_NO_INVOICE, VIEW_MISMATCH, VIEW_DUPLICATE)

REASON_INVOICE_NO = "Same supplier invoice number apart from a DUP/COPY suffix"
REASON_SAME_LINES = "Same supplier, invoice date, items, quantities and rates"

# Staff have bypassed the unique supplier invoice number check by appending a
# word such as "-DUPLICTE"; strip those so the original number still collides.
DUPLICATE_SUFFIX = re.compile(r"(DUPLICATE|DUPLICTE|DUPLCATE|DUP|COPY)\d*$")

DEFAULT_TOLERANCE = 1.0


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	view = filters.view or VIEW_AWAITING
	builders = {
		VIEW_AWAITING: (get_awaiting_columns, get_awaiting_data),
		VIEW_NO_INVOICE: (get_no_invoice_columns, get_no_invoice_data),
		VIEW_MISMATCH: (get_mismatch_columns, get_mismatch_data),
		VIEW_DUPLICATE: (get_duplicate_columns, get_duplicate_data),
	}
	get_columns, get_data = builders[view]
	return get_columns(currency), get_data(filters)


def validate_filters(filters):
	frappe.has_permission("Purchase Invoice", "read", throw=True)
	if not filters.company:
		frappe.throw(_("Please select a Company"))
	if filters.view and filters.view not in VIEWS:
		frappe.throw(_("Unknown view") + ": " + frappe.bold(filters.view))
	if filters.from_date and filters.to_date and getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))
	if not frappe.db.has_column("Purchase Receipt", "custom_supplier_invoice_number"):
		frappe.throw(_("Purchase Receipt has no Supplier Invoice No field on this site"))


# ---------------------------------------------------------------------------
# Pure matching logic (no database access, unit-tested directly)
# ---------------------------------------------------------------------------


def normalise(value):
	"""Upper-case alphanumerics only, so 'in-01 533379' == 'IN01533379'."""
	return re.sub(r"[^A-Z0-9]", "", cstr(value).upper())


def invoice_root(value):
	"""Normalised invoice number with any trailing DUP/COPY marker removed."""
	number = normalise(value)
	stripped = DUPLICATE_SUFFIX.sub("", number)
	return stripped or number


def match_documents(invoices, receipts):
	"""Pair Purchase Invoices with Purchase Receipts.

	invoices: list of dict(name, supplier, bill_no, linked_receipts: set)
	receipts: list of dict(name, supplier, inv)

	Returns (by_number, matched_invoices, matched_receipts):
	  by_number          {invoice: [receipt, ...]} paired on supplier + number
	  matched_invoices   invoices paired by number or by a direct link
	  matched_receipts   receipts paired with some invoice either way
	"""
	live = {r["name"] for r in receipts}
	index = defaultdict(list)
	for r in receipts:
		number = normalise(r.get("inv"))
		if number:
			index[(r["supplier"], number)].append(r["name"])

	by_number, matched_invoices, matched_receipts = {}, set(), set()
	for inv in invoices:
		number = normalise(inv.get("bill_no"))
		hits = list(index.get((inv["supplier"], number), [])) if number else []
		linked = set(inv.get("linked_receipts") or ()) & live
		if hits:
			by_number[inv["name"]] = hits
		if hits or linked:
			matched_invoices.add(inv["name"])
			matched_receipts.update(hits)
			matched_receipts.update(linked)
	return by_number, matched_invoices, matched_receipts


def find_duplicates(receipts, signatures):
	"""Flag receipts that look like the same supplier invoice entered twice.

	receipts:   list of dict(name, supplier, inv, inv_date)
	signatures: {receipt: hashable of its (item, qty, rate) lines}

	Returns {receipt: {"reasons": [...], "related": [...]}}.
	"""
	flagged = defaultdict(lambda: {"reasons": [], "related": set()})

	def flag(group, reason):
		if len(group) < 2:
			return
		for r in group:
			entry = flagged[r["name"]]
			if reason not in entry["reasons"]:
				entry["reasons"].append(reason)
			entry["related"].update(x["name"] for x in group if x["name"] != r["name"])

	by_root, by_lines = defaultdict(list), defaultdict(list)
	for r in receipts:
		root = invoice_root(r.get("inv"))
		if root:
			by_root[(r["supplier"], root)].append(r)
		signature = signatures.get(r["name"])
		if signature and r.get("inv_date"):
			by_lines[(r["supplier"], cstr(r["inv_date"]), signature)].append(r)

	for group in by_root.values():
		flag(group, REASON_INVOICE_NO)
	for group in by_lines.values():
		flag(group, REASON_SAME_LINES)

	return {name: {"reasons": v["reasons"], "related": sorted(v["related"])} for name, v in flagged.items()}


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


def get_invoices(filters):
	"""Submitted, non-return Purchase Invoices that book stock items without
	receiving them (Update Stock off), with the receipts their items point at."""
	pi = frappe.qb.DocType("Purchase Invoice")
	pii = frappe.qb.DocType("Purchase Invoice Item")
	item = frappe.qb.DocType("Item")

	query = (
		frappe.qb.from_(pi)
		.join(pii)
		.on(pii.parent == pi.name)
		.join(item)
		.on(item.name == pii.item_code)
		.select(
			pi.name,
			pi.supplier,
			pi.bill_no,
			pi.posting_date,
			pi.base_grand_total,
			pii.purchase_receipt,
		)
		.where(
			(pi.docstatus == 1)
			& (pi.update_stock == 0)
			& (pi.is_return == 0)
			& (pi.company == filters.company)
			& (item.is_stock_item == 1)
		)
	)
	if filters.supplier:
		query = query.where(pi.supplier == filters.supplier)

	invoices = {}
	for row in query.run(as_dict=True):
		doc = invoices.setdefault(
			row.name,
			{
				"name": row.name,
				"supplier": row.supplier,
				"bill_no": row.bill_no,
				"posting_date": row.posting_date,
				"amount": flt(row.base_grand_total),
				"linked_receipts": set(),
			},
		)
		if row.purchase_receipt:
			doc["linked_receipts"].add(row.purchase_receipt)
	return list(invoices.values())


def get_receipts(filters):
	pr = frappe.qb.DocType("Purchase Receipt")
	query = (
		frappe.qb.from_(pr)
		.select(
			pr.name,
			pr.supplier,
			pr.posting_date,
			pr.base_grand_total,
			pr.custom_supplier_invoice_number.as_("inv"),
			pr.custom_supplier_invoice_date.as_("inv_date"),
		)
		.where((pr.docstatus == 1) & (pr.is_return == 0) & (pr.company == filters.company))
	)
	if filters.supplier:
		query = query.where(pr.supplier == filters.supplier)

	return [
		{
			"name": r.name,
			"supplier": r.supplier,
			"posting_date": r.posting_date,
			"amount": flt(r.base_grand_total),
			"inv": r.inv,
			"inv_date": r.inv_date,
		}
		for r in query.run(as_dict=True)
	]


def get_line_signatures(receipt_names):
	"""{receipt: sorted tuple of (item_code, qty, rate)} for the given receipts."""
	if not receipt_names:
		return {}
	pri = frappe.qb.DocType("Purchase Receipt Item")
	rows = (
		frappe.qb.from_(pri)
		.select(pri.parent, pri.item_code, pri.qty, pri.rate)
		.where(pri.parent.isin(list(receipt_names)))
		.run(as_dict=True)
	)
	lines = defaultdict(list)
	for r in rows:
		lines[r.parent].append((cstr(r.item_code), flt(r.qty, 3), flt(r.rate, 4)))
	return {name: tuple(sorted(v)) for name, v in lines.items()}


def in_range(posting_date, filters):
	posting_date = getdate(posting_date)
	if filters.from_date and posting_date < getdate(filters.from_date):
		return False
	if filters.to_date and posting_date > getdate(filters.to_date):
		return False
	return True


def get_tolerance(filters):
	return flt(filters.tolerance) if filters.tolerance not in (None, "") else DEFAULT_TOLERANCE


def amount_candidates(documents, matched, supplier, amount, tolerance):
	"""Unmatched documents of the same supplier whose total is within tolerance."""
	return [
		d["name"]
		for d in documents
		if d["supplier"] == supplier and d["name"] not in matched and abs(d["amount"] - amount) <= tolerance
	][:3]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def get_awaiting_columns(currency):
	return [
		{"label": _("Purchase Invoice"), "fieldname": "purchase_invoice", "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 220},
		{"label": _("Supplier Invoice No"), "fieldname": "bill_no", "fieldtype": "Data", "width": 150},
		{"label": _("Invoice Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Days Waiting"), "fieldname": "age", "fieldtype": "Int", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 220},
		{"label": _("Possible Receipt (same amount)"), "fieldname": "candidates", "fieldtype": "Data", "width": 220},
	]


def get_awaiting_data(filters):
	invoices, receipts = get_invoices(filters), get_receipts(filters)
	_by_number, matched_invoices, matched_receipts = match_documents(invoices, receipts)
	tolerance, min_age = get_tolerance(filters), cint(filters.min_age_days)

	rows = []
	for inv in invoices:
		if inv["name"] in matched_invoices or not in_range(inv["posting_date"], filters):
			continue
		age = date_diff(today(), inv["posting_date"])
		if age < min_age:
			continue
		candidates = amount_candidates(receipts, matched_receipts, inv["supplier"], inv["amount"], tolerance)
		rows.append(
			{
				"purchase_invoice": inv["name"],
				"posting_date": inv["posting_date"],
				"supplier": inv["supplier"],
				"bill_no": inv["bill_no"],
				"amount": inv["amount"],
				"age": age,
				"status": _("Possible receipt - check invoice no") if candidates else _("No receipt entered"),
				"candidates": ", ".join(candidates),
			}
		)
	return sorted(rows, key=lambda r: r["age"], reverse=True)


def get_no_invoice_columns(currency):
	return [
		{"label": _("Purchase Receipt"), "fieldname": "purchase_receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 150},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 220},
		{"label": _("Supplier Invoice No"), "fieldname": "inv", "fieldtype": "Data", "width": 150},
		{"label": _("Receipt Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Days Waiting"), "fieldname": "age", "fieldtype": "Int", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 220},
		{"label": _("Possible Invoice (same amount)"), "fieldname": "candidates", "fieldtype": "Data", "width": 220},
	]


def get_no_invoice_data(filters):
	invoices, receipts = get_invoices(filters), get_receipts(filters)
	_by_number, matched_invoices, matched_receipts = match_documents(invoices, receipts)
	tolerance, min_age = get_tolerance(filters), cint(filters.min_age_days)

	rows = []
	for pr in receipts:
		if pr["name"] in matched_receipts or not in_range(pr["posting_date"], filters):
			continue
		age = date_diff(today(), pr["posting_date"])
		if age < min_age:
			continue
		candidates = amount_candidates(invoices, matched_invoices, pr["supplier"], pr["amount"], tolerance)
		rows.append(
			{
				"purchase_receipt": pr["name"],
				"posting_date": pr["posting_date"],
				"supplier": pr["supplier"],
				"inv": pr["inv"],
				"amount": pr["amount"],
				"age": age,
				"status": _("Possible invoice - check invoice no") if candidates else _("No invoice entered"),
				"candidates": ", ".join(candidates),
			}
		)
	return sorted(rows, key=lambda r: r["age"], reverse=True)


def get_mismatch_columns(currency):
	return [
		{"label": _("Purchase Invoice"), "fieldname": "purchase_invoice", "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 220},
		{"label": _("Supplier Invoice No"), "fieldname": "bill_no", "fieldtype": "Data", "width": 150},
		{"label": _("Invoice Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Purchase Receipt"), "fieldname": "receipts", "fieldtype": "Data", "width": 170},
		{"label": _("Receipt Amount"), "fieldname": "receipt_amount", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Difference (Invoice - Receipt)"), "fieldname": "difference", "fieldtype": "Currency", "options": currency, "width": 150},
	]


def get_mismatch_data(filters):
	invoices, receipts = get_invoices(filters), get_receipts(filters)
	by_number, _matched_invoices, _matched_receipts = match_documents(invoices, receipts)
	receipt_amount = {r["name"]: r["amount"] for r in receipts}
	tolerance = get_tolerance(filters)

	rows = []
	for inv in invoices:
		hits = by_number.get(inv["name"])
		if not hits or not in_range(inv["posting_date"], filters):
			continue
		total = sum(receipt_amount[name] for name in hits)
		difference = flt(inv["amount"] - total, 2)
		if abs(difference) <= tolerance:
			continue
		rows.append(
			{
				"purchase_invoice": inv["name"],
				"posting_date": inv["posting_date"],
				"supplier": inv["supplier"],
				"bill_no": inv["bill_no"],
				"amount": inv["amount"],
				"receipts": ", ".join(hits),
				"receipt_amount": flt(total, 2),
				"difference": difference,
			}
		)
	return sorted(rows, key=lambda r: abs(r["difference"]), reverse=True)


def get_duplicate_columns(currency):
	return [
		{"label": _("Purchase Receipt"), "fieldname": "purchase_receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 150},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 220},
		{"label": _("Supplier Invoice No"), "fieldname": "inv", "fieldtype": "Data", "width": 170},
		{"label": _("Supplier Invoice Date"), "fieldname": "inv_date", "fieldtype": "Date", "width": 120},
		{"label": _("Receipt Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Why Flagged"), "fieldname": "reason", "fieldtype": "Data", "width": 330},
		{"label": _("Related Receipts"), "fieldname": "related", "fieldtype": "Data", "width": 220},
	]


def get_duplicate_data(filters):
	receipts = get_receipts(filters)
	flagged = find_duplicates(receipts, get_line_signatures([r["name"] for r in receipts]))

	rows = []
	for pr in receipts:
		hit = flagged.get(pr["name"])
		if not hit or not in_range(pr["posting_date"], filters):
			continue
		rows.append(
			{
				"purchase_receipt": pr["name"],
				"posting_date": pr["posting_date"],
				"supplier": pr["supplier"],
				"inv": pr["inv"],
				"inv_date": pr["inv_date"],
				"amount": pr["amount"],
				"reason": "; ".join(_(reason) for reason in hit["reasons"]),
				"related": ", ".join(hit["related"]),
			}
		)
	return sorted(rows, key=lambda r: (r["supplier"], cstr(r["inv"]), r["purchase_receipt"]))
