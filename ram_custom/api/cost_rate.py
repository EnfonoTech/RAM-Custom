from __future__ import annotations

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_cost_rate(item_code: str, company: str, warehouse: str) -> float:
	"""Return Bin valuation rate as "Cost Rate" for an item+warehouse."""
	if not item_code or not company:
		return 0.0

	try:
		from erpnext.stock.get_item_details import get_valuation_rate
	except ImportError:
		return 0.0

	# When warehouse is missing/empty, ERPNext falls back to the item's default warehouse(s).
	out = get_valuation_rate(item_code, company, warehouse or None)
	return flt(out.get("valuation_rate") or 0.0)

