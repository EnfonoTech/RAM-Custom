# Copyright (c) 2026, ramees and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from ram_custom.api.inter_company_transfer import _get_historical_valuation_rate


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	columns = _columns()
	rows = _rows(filters)
	return columns, rows


def _columns() -> list[dict]:
	return [
		{
			"fieldname": "inter_company_transfer",
			"label": _("Inter Company Transfer"),
			"fieldtype": "Link",
			"options": "Inter Company Transfer",
			"width": 180,
		},
		{
			"fieldname": "posting_date",
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"fieldname": "from_company",
			"label": _("From Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 140,
		},
		{
			"fieldname": "to_company",
			"label": _("To Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 140,
		},
		{
			"fieldname": "item_code",
			"label": _("Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{
			"fieldname": "source_warehouse",
			"label": _("Source Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 160,
		},
		{
			"fieldname": "stock_qty",
			"label": _("Stock Qty"),
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"fieldname": "previous_baseline",
			"label": _("Reconciled Baseline"),
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"fieldname": "current_sle_cost",
			"label": _("Current SLE Cost"),
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"fieldname": "variance",
			"label": _("Variance"),
			"fieldtype": "Currency",
			"width": 120,
		},
	]


def _rows(filters: frappe._dict) -> list[dict]:
	conditions = ["ict.docstatus = 1"]
	params: dict = {}

	if filters.get("from_company"):
		conditions.append("ict.from_company = %(from_company)s")
		params["from_company"] = filters.from_company
	if filters.get("to_company"):
		conditions.append("ict.to_company = %(to_company)s")
		params["to_company"] = filters.to_company
	if filters.get("from_date"):
		conditions.append("ict.posting_date >= %(from_date)s")
		params["from_date"] = getdate(filters.from_date)
	if filters.get("to_date"):
		conditions.append("ict.posting_date <= %(to_date)s")
		params["to_date"] = getdate(filters.to_date)
	if filters.get("inter_company_transfer"):
		conditions.append("ict.name = %(name)s")
		params["name"] = filters.inter_company_transfer

	where = " and ".join(conditions)
	rows = frappe.db.sql(
		f"""
		select
			ict.name as inter_company_transfer,
			ict.posting_date,
			ict.posting_time,
			ict.from_company,
			ict.to_company,
			child.name as ict_item_row,
			child.item_code,
			child.source_warehouse,
			child.qty,
			child.conversion_factor,
			child.reconciled_cost_value
		from `tabInter Company Transfer` ict
		inner join `tabInter Company Transfer Item` child
			on child.parent = ict.name and child.parenttype = 'Inter Company Transfer'
		where {where}
		order by ict.posting_date desc, ict.name desc
		""",
		params,
		as_dict=True,
	)

	hide_zero = not filters.get("show_zero_variance")
	threshold = flt(filters.get("variance_threshold") or 0.01)

	out = []
	for r in rows:
		rate = _get_historical_valuation_rate(
			r.item_code,
			r.source_warehouse,
			str(r.posting_date) if r.posting_date else None,
			r.posting_time,
		)
		stock_qty = flt(r.qty) * flt(r.conversion_factor or 1)
		current_cost = flt(stock_qty * flt(rate), 2)
		previous = flt(r.reconciled_cost_value, 2)
		variance = flt(current_cost - previous, 2)
		if hide_zero and abs(variance) < threshold:
			continue
		out.append(
			{
				"inter_company_transfer": r.inter_company_transfer,
				"posting_date": r.posting_date,
				"from_company": r.from_company,
				"to_company": r.to_company,
				"item_code": r.item_code,
				"source_warehouse": r.source_warehouse,
				"stock_qty": stock_qty,
				"previous_baseline": previous,
				"current_sle_cost": current_cost,
				"variance": variance,
			}
		)
	return out
