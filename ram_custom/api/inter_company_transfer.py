from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

TRANSFER_TAG = "ICT"


def _parse_payload(payload: str | dict) -> dict:
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except Exception:
			frappe.throw(_("Invalid JSON payload"))
	if not isinstance(payload, dict):
		frappe.throw(_("Payload must be a JSON object"))
	return payload


def _marker(transfer_id: str, step: str) -> str:
	return f"[{TRANSFER_TAG}:{transfer_id}:{step}]"


def _is_duplicate(doctype: str, fieldname: str, marker: str) -> bool:
	return bool(frappe.db.exists(doctype, {fieldname: ["like", f"%{marker}%"]}))


def _warehouse_belongs_to_company(warehouse: str, company: str) -> bool:
	warehouse_company = frappe.db.get_value("Warehouse", warehouse, "company", cache=True)
	return warehouse_company == company


def _account_belongs_to_company(account: str, company: str) -> bool:
	account_company = frappe.db.get_value("Account", account, "company", cache=True)
	return account_company == company


def _get_company_pair_account_row(from_company: str, to_company: str) -> dict:
	if not from_company or not to_company:
		return {}
	rows = frappe.get_all(
		"Inter Company Transfer Company Account",
		filters={
			"from_company": from_company,
			"to_company": to_company,
			"parenttype": "Inter Company Transfer Settings",
		},
		fields=[
			"from_company",
			"to_company",
			"cost_of_branch_sales_account",
			"branch_sales_clearing_account",
			"from_company_receivable_account",
			"to_company_payable_account",
			"unrealized_branch_margin_account",
		],
		limit=1,
	)
	return rows[0] if rows else {}


@frappe.whitelist()
def get_transfer_account_heads(from_company: str, to_company: str) -> dict:
	"""Return configured account heads from settings for selected From/To pair."""
	row = _get_company_pair_account_row(from_company, to_company)

	return {
		"cost_of_branch_sales_account": row.get("cost_of_branch_sales_account"),
		"branch_sales_clearing_account": row.get("branch_sales_clearing_account"),
		"from_company_receivable_account": row.get("from_company_receivable_account"),
		"to_company_payable_account": row.get("to_company_payable_account"),
		"unrealized_branch_margin_account": row.get("unrealized_branch_margin_account"),
	}


def _get_bin_valuation_rate(item_code: str, warehouse: str) -> float:
	"""Valuation rate per stock UOM; no throw (safe for live form / API preview)."""
	if not item_code or not warehouse:
		return 0.0
	rate = frappe.db.get_value(
		"Bin",
		{"item_code": item_code, "warehouse": warehouse},
		"valuation_rate",
	)
	return flt(rate)


@frappe.whitelist()
def get_item_valuation_rate(item_code: str, warehouse: str) -> float:
	"""Return valuation rate from Bin for item+warehouse (per stock UOM)."""
	return _get_bin_valuation_rate(item_code, warehouse)


def _validate_accounts(from_company, to_company, data):
	for account in (
		data.get("cost_of_branch_sales_account"),
		data.get("branch_sales_clearing_account"),
		data.get("from_company_receivable_account"),
	):
		if not account:
			frappe.throw(_("From-company accounts must be set"))
		if not _account_belongs_to_company(account, from_company):
			frappe.throw(
				_("Account {0} must belong to company {1}").format(account, from_company)
			)

	payable = data.get("to_company_payable_account")
	if not payable:
		frappe.throw(_("To company payable account must be set"))
	if not _account_belongs_to_company(payable, to_company):
		frappe.throw(
			_("Account {0} must belong to company {1}").format(payable, to_company)
		)

	margin_acc = data.get("unrealized_branch_margin_account")
	if margin_acc and not _account_belongs_to_company(margin_acc, from_company):
		frappe.throw(
			_("Account {0} must belong to company {1}").format(margin_acc, from_company)
		)


def _rollback_created_vouchers(created: list[tuple[str, str]]) -> None:
	"""Cancel submitted or delete draft docs created during a failed posting."""
	for doctype, name in reversed(created):
		if not name:
			continue
		try:
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.cancel()
			elif doc.docstatus == 0:
				frappe.delete_doc(doctype, name, force=1)
		except Exception:
			frappe.log_error(
				title=_("Rollback failed for {0} {1}").format(doctype, name),
				message=frappe.get_traceback(),
			)


def _normalize_items(data: dict) -> list[dict]:
	items = data.get("items") or []
	default_source_warehouse = data.get("source_warehouse")
	default_target_warehouse = data.get("target_warehouse")
	if not items:
		# backward compatibility: single-item payload
		items = [
			{
				"item_code": data.get("item_code"),
				"qty": data.get("qty"),
				"cost_rate": data.get("cost_rate") or 0,
				"transfer_rate": data.get("transfer_rate"),
				"source_warehouse": default_source_warehouse,
				"target_warehouse": default_target_warehouse,
			}
		]

	if not isinstance(items, list):
		frappe.throw(_("Items must be a list"))

	normalized = []

	for row in items:
		item_code = (row or {}).get("item_code")
		qty = flt((row or {}).get("qty"))
		cost_rate = flt((row or {}).get("cost_rate"))
		transfer_rate = flt((row or {}).get("transfer_rate"))
		source_warehouse = (row or {}).get("source_warehouse") or default_source_warehouse
		target_warehouse = (row or {}).get("target_warehouse") or default_target_warehouse
		uom = (row or {}).get("uom")
		stock_uom = (row or {}).get("stock_uom")
		conversion_factor = flt((row or {}).get("conversion_factor") or 1)

		if not item_code:
			frappe.throw(_("Each row must have Item Code"))
		if qty <= 0:
			frappe.throw(_("Quantity must be greater than zero for item {0}").format(item_code))
		if transfer_rate <= 0:
			frappe.throw(
				_("Transfer Rate must be greater than zero for item {0}").format(item_code)
			)
		if cost_rate < 0:
			frappe.throw(_("Cost Rate cannot be negative for item {0}").format(item_code))
		if not source_warehouse or not target_warehouse:
			frappe.throw(_("Source/Target Warehouse is required for item {0}").format(item_code))
		if conversion_factor <= 0:
			frappe.throw(_("Conversion Factor must be greater than zero for item {0}").format(item_code))

		normalized.append(
			{
				"item_code": item_code,
				"qty": qty,
				"cost_rate": cost_rate,
				"transfer_rate": transfer_rate,
				"source_warehouse": source_warehouse,
				"target_warehouse": target_warehouse,
				"uom": uom,
				"stock_uom": stock_uom,
				"conversion_factor": conversion_factor,
			}
		)

	return normalized


def _apply_server_valuation_and_totals(items: list[dict]) -> tuple[float, float]:
	"""Recalculate cost from Bin (authoritative) and line/totals using stock qty."""
	total_cost_value = 0.0
	total_transfer_value = 0.0
	for row in items:
		item_code = row["item_code"]
		source_wh = row["source_warehouse"]
		cost_rate = _get_bin_valuation_rate(item_code, source_wh)
		is_stock = frappe.db.get_value("Item", item_code, "is_stock_item")
		if is_stock and flt(cost_rate) <= 0:
			frappe.throw(
				_(
					"No valuation rate for item {0} in warehouse {1}. "
					"Receive stock or revalue before submitting."
				).format(item_code, source_wh)
			)
		row["cost_rate"] = cost_rate
		stock_qty = flt(row["qty"]) * flt(row.get("conversion_factor") or 1)
		row["cost_value"] = flt(stock_qty * cost_rate)
		row["transfer_value"] = flt(stock_qty * flt(row["transfer_rate"]))
		total_cost_value += row["cost_value"]
		total_transfer_value += row["transfer_value"]
	return total_cost_value, total_transfer_value


@frappe.whitelist()
def create_inter_company_transfer(payload: str | dict) -> dict:
	"""
	Automates inter-company transfer without Sales/Purchase Invoices:
	1) Material Issue (From Company, at cost)
	2) Material Receipt (To Company, at transfer rate)
	3) JE in From Company: Receivable Dr / Branch Sales Clearing Cr
	"""
	data = _parse_payload(payload)
	required = [
		"transfer_id",
		"from_company",
		"to_company",
		"cost_of_branch_sales_account",
		"branch_sales_clearing_account",
		"from_company_receivable_account",
		"to_company_payable_account",
		"unrealized_branch_margin_account",
	]
	for key in required:
		if not data.get(key):
			frappe.throw(_("Missing required field: {0}").format(key))

	transfer_id = str(data.get("transfer_id")).strip()
	from_company = data.get("from_company")
	to_company = data.get("to_company")
	if from_company == to_company:
		frappe.throw(_("From Company and To Company cannot be the same"))

	_validate_accounts(from_company, to_company, data)
	items = _normalize_items(data)
	total_cost_value, total_transfer_value = _apply_server_valuation_and_totals(items)
	if flt(total_transfer_value) < flt(total_cost_value):
		frappe.throw(
			_(
				"Total transfer value ({0}) cannot be less than total cost value ({1}). "
				"Increase transfer rates or reduce cost."
			).format(total_transfer_value, total_cost_value)
		)
	for row in items:
		if not _warehouse_belongs_to_company(row["source_warehouse"], from_company):
			frappe.throw(
				_("Source Warehouse {0} must belong to {1}").format(
					row["source_warehouse"], from_company
				)
			)
		if not _warehouse_belongs_to_company(row["target_warehouse"], to_company):
			frappe.throw(
				_("Target Warehouse {0} must belong to {1}").format(
					row["target_warehouse"], to_company
				)
			)

	issue_marker = _marker(transfer_id, "ISSUE")
	receipt_marker = _marker(transfer_id, "RECEIPT")
	je_marker = _marker(transfer_id, "RECEIVABLE_JE")

	if _is_duplicate("Stock Entry", "remarks", issue_marker):
		frappe.throw(_("Transfer {0} already has an Issue Stock Entry").format(transfer_id))
	if _is_duplicate("Stock Entry", "remarks", receipt_marker):
		frappe.throw(
			_("Transfer {0} already has a Receipt Stock Entry").format(transfer_id)
		)
	if _is_duplicate("Journal Entry", "user_remark", je_marker):
		frappe.throw(_("Transfer {0} already has a Receivable JE").format(transfer_id))

	posting_date = getdate(data.get("posting_date") or nowdate())

	created: list[tuple[str, str]] = []

	try:
		issue = frappe.new_doc("Stock Entry")
		issue.stock_entry_type = "Material Issue"
		issue.company = from_company
		issue.posting_date = posting_date
		issue.remarks = f"{issue_marker} Inter-company issue at cost"
		for row in items:
			issue.append(
				"items",
				{
					"item_code": row["item_code"],
					"qty": row["qty"],
					"uom": row.get("uom"),
					"stock_uom": row.get("stock_uom"),
					"conversion_factor": row.get("conversion_factor") or 1,
					"s_warehouse": row["source_warehouse"],
					"expense_account": data.get("cost_of_branch_sales_account"),
				},
			)
		issue.insert()
		issue.submit()
		created.append(("Stock Entry", issue.name))

		receipt = frappe.new_doc("Stock Entry")
		receipt.stock_entry_type = "Material Receipt"
		receipt.company = to_company
		receipt.posting_date = posting_date
		receipt.remarks = f"{receipt_marker} Inter-company receipt at transfer value"
		for row in items:
			receipt.append(
				"items",
				{
					"item_code": row["item_code"],
					"qty": row["qty"],
					"uom": row.get("uom"),
					"stock_uom": row.get("stock_uom"),
					"conversion_factor": row.get("conversion_factor") or 1,
					"t_warehouse": row["target_warehouse"],
					"basic_rate": row["transfer_rate"],
					"expense_account": data.get("to_company_payable_account"),
				},
			)
		receipt.insert()
		receipt.submit()
		created.append(("Stock Entry", receipt.name))

		markup_value = flt(total_transfer_value - total_cost_value)

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = from_company
		je.posting_date = posting_date
		je.user_remark = (
			f"{je_marker} Inter-company receivable creation for transfer {transfer_id}"
		)
		# Dr Company B - Receivable (total transfer value)
		je.append(
			"accounts",
			{
				"account": data.get("from_company_receivable_account"),
				"debit_in_account_currency": total_transfer_value,
			},
		)
		# Cr Branch Sales Clearing (at total cost)
		je.append(
			"accounts",
			{
				"account": data.get("branch_sales_clearing_account"),
				"credit_in_account_currency": total_cost_value,
			},
		)
		# Cr markup (validated: transfer >= cost, so markup >= 0)
		if markup_value > 0:
			je.append(
				"accounts",
				{
					"account": data.get("unrealized_branch_margin_account"),
					"credit_in_account_currency": markup_value,
				},
			)
		je.insert()
		je.submit()
		created.append(("Journal Entry", je.name))

		return {
			"transfer_id": transfer_id,
			"issue_stock_entry": issue.name,
			"receipt_stock_entry": receipt.name,
			"receivable_journal_entry": je.name,
			"cost_value": total_cost_value,
			"transfer_value": total_transfer_value,
		}
	except Exception:
		_rollback_created_vouchers(created)
		raise


@frappe.whitelist()
def settle_inter_company_transfer(payload: str | dict) -> dict:
	"""
	Settle inter-company amount using Journal Entries (no SI/PI):
	- Company B: Payable Dr / Bank Cr
	- Company A: Bank Dr / Receivable Cr
	"""
	data = _parse_payload(payload)
	required = [
		"transfer_id",
		"posting_date",
		"transfer_value",
		"from_company",
		"to_company",
		"from_company_receivable_account",
		"to_company_payable_account",
		"from_company_bank_account",
		"to_company_bank_account",
	]
	for key in required:
		if not data.get(key):
			frappe.throw(_("Missing required field: {0}").format(key))

	transfer_id = str(data.get("transfer_id")).strip()
	posting_date = getdate(data.get("posting_date"))
	transfer_value = flt(data.get("transfer_value"))
	if transfer_value <= 0:
		frappe.throw(_("Transfer value must be greater than zero"))

	from_company = data.get("from_company")
	to_company = data.get("to_company")
	if from_company == to_company:
		frappe.throw(_("From Company and To Company cannot be the same"))

	from_receivable = data.get("from_company_receivable_account")
	to_payable = data.get("to_company_payable_account")
	from_bank = data.get("from_company_bank_account")
	to_bank = data.get("to_company_bank_account")

	for account in (from_receivable, from_bank):
		if not _account_belongs_to_company(account, from_company):
			frappe.throw(
				_("Account {0} must belong to company {1}").format(account, from_company)
			)
	for account in (to_payable, to_bank):
		if not _account_belongs_to_company(account, to_company):
			frappe.throw(
				_("Account {0} must belong to company {1}").format(account, to_company)
			)

	pay_marker = _marker(transfer_id, "PAYMENT_B")
	receive_marker = _marker(transfer_id, "RECEIPT_A")
	if _is_duplicate("Journal Entry", "user_remark", pay_marker):
		frappe.throw(_("Transfer {0} already has Company B payment JE").format(transfer_id))
	if _is_duplicate("Journal Entry", "user_remark", receive_marker):
		frappe.throw(_("Transfer {0} already has Company A receipt JE").format(transfer_id))

	je_b = frappe.new_doc("Journal Entry")
	je_b.voucher_type = "Journal Entry"
	je_b.company = to_company
	je_b.posting_date = posting_date
	je_b.user_remark = f"{pay_marker} Inter-company payable settlement for {transfer_id}"
	je_b.append(
		"accounts",
		{
			"account": to_payable,
			"debit_in_account_currency": transfer_value,
		},
	)
	je_b.append(
		"accounts",
		{
			"account": to_bank,
			"credit_in_account_currency": transfer_value,
		},
	)
	je_b.insert()
	je_b.submit()

	je_a = frappe.new_doc("Journal Entry")
	je_a.voucher_type = "Journal Entry"
	je_a.company = from_company
	je_a.posting_date = posting_date
	je_a.user_remark = f"{receive_marker} Inter-company receivable settlement for {transfer_id}"
	je_a.append(
		"accounts",
		{
			"account": from_bank,
			"debit_in_account_currency": transfer_value,
		},
	)
	je_a.append(
		"accounts",
		{
			"account": from_receivable,
			"credit_in_account_currency": transfer_value,
		},
	)
	je_a.insert()
	je_a.submit()

	return {
		"transfer_id": transfer_id,
		"payment_je_company_b": je_b.name,
		"receipt_je_company_a": je_a.name,
	}


@frappe.whitelist()
def post_period_end_deferral(payload: str | dict) -> dict:
	"""
	Company A month-end deferral:
	Dr Branch Sales Clearing (transfer value)
	Cr Cost of Branch Sales (cost value)
	Cr Unrealized Branch Margin (markup)
	"""
	data = _parse_payload(payload)
	required = [
		"transfer_id",
		"posting_date",
		"company",
		"transfer_value",
		"cost_value",
		"branch_sales_clearing_account",
		"cost_of_branch_sales_account",
		"unrealized_branch_margin_account",
	]
	for key in required:
		if not data.get(key):
			frappe.throw(_("Missing required field: {0}").format(key))

	transfer_id = str(data.get("transfer_id")).strip()
	posting_date = getdate(data.get("posting_date"))
	company = data.get("company")
	transfer_value = flt(data.get("transfer_value"))
	cost_value = flt(data.get("cost_value"))
	if transfer_value <= 0 or cost_value <= 0:
		frappe.throw(_("Transfer value and cost value must be greater than zero"))
	if transfer_value < cost_value:
		frappe.throw(_("Transfer value cannot be less than cost value"))

	markup_value = flt(transfer_value - cost_value)
	branch_sales_clearing = data.get("branch_sales_clearing_account")
	cost_of_branch_sales = data.get("cost_of_branch_sales_account")
	unrealized_margin = data.get("unrealized_branch_margin_account")

	for account in (branch_sales_clearing, cost_of_branch_sales, unrealized_margin):
		if not _account_belongs_to_company(account, company):
			frappe.throw(_("Account {0} must belong to company {1}").format(account, company))

	deferral_marker = _marker(transfer_id, "DEFERRAL")
	if _is_duplicate("Journal Entry", "user_remark", deferral_marker):
		frappe.throw(_("Transfer {0} already has period-end deferral JE").format(transfer_id))

	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = posting_date
	je.user_remark = f"{deferral_marker} Month-end deferral for transfer {transfer_id}"
	je.append(
		"accounts",
		{
			"account": branch_sales_clearing,
			"debit_in_account_currency": transfer_value,
		},
	)
	je.append(
		"accounts",
		{
			"account": cost_of_branch_sales,
			"credit_in_account_currency": cost_value,
		},
	)
	if markup_value > 0:
		je.append(
			"accounts",
			{
				"account": unrealized_margin,
				"credit_in_account_currency": markup_value,
			},
		)
	je.insert()
	je.submit()

	return {
		"transfer_id": transfer_id,
		"deferral_journal_entry": je.name,
		"markup_value": markup_value,
	}


def run_month_end_deferral_for_open_transfers():
	"""Deprecated: period-end deferral is not part of the current workflow."""
	return


def block_inter_company_invoices(doc, method=None):
	"""Disallow SI/PI usage for any inter-company transfer pattern."""
	if getattr(frappe.flags, "in_import", False):
		return
	if doc.doctype == "Sales Invoice" and (
		doc.get("custom_inter_company_branch")
		or doc.get("is_internal_customer")
		or doc.get("represents_company")
	):
		frappe.throw(
			_(
				"Sales Invoice is not allowed for inter-company stock transfers. "
				"Use Stock Entry + Journal Entry flow."
			)
		)

	if doc.doctype == "Purchase Invoice" and (
		doc.get("custom_inter_company_branch")
		or doc.get("inter_company_invoice_reference")
		or doc.get("is_internal_supplier")
		or doc.get("represents_company")
	):
		frappe.throw(
			_(
				"Purchase Invoice is not allowed for inter-company stock transfers. "
				"Use Stock Entry + Journal Entry flow."
			)
		)
