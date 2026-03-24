# Copyright (c) 2026, ramees and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ram_custom.api.inter_company_transfer import (
	apply_default_transfer_rates_from_price_list,
	create_inter_company_transfer,
	get_item_valuation_rate,
	get_transfer_account_heads,
)


class InterCompanyTransfer(Document):
	def validate(self):
		if self.amended_from:
			self.issue_stock_entry = None
			self.receipt_stock_entry = None
			self.receivable_journal_entry = None

		self._apply_account_heads_from_settings()
		apply_default_transfer_rates_from_price_list(self)
		if self.is_remote_transfer:
			if not self.remote_company:
				frappe.throw(_("Remote Company is required for remote transfer"))
		else:
			if not self.to_company:
				frappe.throw(_("To Company is required for local transfer"))
			if self.from_company and self.to_company and self.from_company == self.to_company:
				frappe.throw(_("From Company and To Company cannot be the same"))
		if not self.items:
			frappe.throw(_("Add at least one item row"))

		total_cost_value = 0.0
		total_transfer_value = 0.0
		for row in self.items:
			if not row.item_code:
				frappe.throw(_("Item is required in all rows"))
			if flt(row.qty) <= 0:
				frappe.throw(_("Qty must be greater than zero in all rows"))
			if flt(row.transfer_rate) <= 0:
				frappe.throw(_("Transfer Rate must be greater than zero in all rows"))
			if not row.source_warehouse:
				row.source_warehouse = self.default_source_warehouse
			if not self.is_remote_transfer and not row.target_warehouse:
				row.target_warehouse = self.default_target_warehouse
			if not row.source_warehouse:
				frappe.throw(_("Source Warehouse is required in each row"))
			if not self.is_remote_transfer and not row.target_warehouse:
				frappe.throw(_("Target Warehouse is required in each row"))
			if flt(row.conversion_factor) <= 0:
				frappe.throw(_("Conversion Factor must be greater than zero in all rows"))
			row.cost_rate = get_item_valuation_rate(row.item_code, row.source_warehouse)
			is_stock = frappe.db.get_value("Item", row.item_code, "is_stock_item")
			if is_stock and flt(row.cost_rate) <= 0:
				frappe.throw(
					_(
						"No valuation rate for item {0} in warehouse {1}. "
						"Receive stock or revalue before saving."
					).format(row.item_code, row.source_warehouse)
				)
			stock_qty = flt(row.qty) * flt(row.conversion_factor or 1)
			row.cost_value = flt(stock_qty * row.cost_rate)
			row.transfer_value = flt(stock_qty * row.transfer_rate)
			row.markup_value = flt(row.transfer_value) - flt(row.cost_value)
			total_cost_value += row.cost_value
			total_transfer_value += row.transfer_value

		self.transfer_id = self.name or self.transfer_id
		self.cost_value = total_cost_value
		self.transfer_value = total_transfer_value
		self.markup_value = flt(self.transfer_value) - flt(self.cost_value)
		if flt(self.transfer_value) < flt(self.cost_value):
			frappe.throw(
				_(
					"Total transfer value cannot be less than total cost value. "
					"Increase transfer rates or check quantities/UOM."
				)
			)

	def on_submit(self):
		if self.issue_stock_entry or self.receipt_stock_entry or self.receivable_journal_entry:
			frappe.throw(
				_("Linked vouchers already exist. Cancel and amend instead of re-submitting.")
			)
		result = create_inter_company_transfer(
			{
				"transfer_id": self.name,
				"posting_date": self.posting_date,
				"from_company": self.from_company,
				"to_company": self.to_company,
				"remote_company": self.remote_company,
				"source_warehouse": self.default_source_warehouse,
				"target_warehouse": self.default_target_warehouse,
				"cost_of_branch_sales_account": self.cost_of_branch_sales_account,
				"branch_sales_clearing_account": self.branch_sales_clearing_account,
				"from_company_receivable_account": self.from_company_receivable_account,
				"to_company_payable_account": self.to_company_payable_account,
				"unrealized_branch_margin_account": self.unrealized_branch_margin_account,
				"is_remote_transfer": self.is_remote_transfer,
				"items": [
					{
						"item_code": row.item_code,
						"qty": row.qty,
						"cost_rate": row.cost_rate,
						"transfer_rate": row.transfer_rate,
						"uom": row.uom,
						"stock_uom": row.stock_uom,
						"conversion_factor": row.conversion_factor,
						"source_warehouse": row.source_warehouse,
						"target_warehouse": row.target_warehouse,
					}
					for row in self.items
				],
			}
		)
		self.db_set("issue_stock_entry", result.get("issue_stock_entry"))
		self.db_set("receipt_stock_entry", result.get("receipt_stock_entry"))
		self.db_set("receivable_journal_entry", result.get("receivable_journal_entry"))
		self.db_set("transfer_id", self.name)

	def _apply_account_heads_from_settings(self):
		if not self.from_company:
			return
		if self.is_remote_transfer and not self.remote_company:
			return
		if not self.is_remote_transfer and not self.to_company:
			return
		heads = get_transfer_account_heads(
			from_company=self.from_company,
			to_company=self.to_company,
			remote_company=self.remote_company,
			is_remote_transfer=self.is_remote_transfer,
		)
		if not any(heads.values()):
			return
		if heads.get("cost_of_branch_sales_account") and not self.cost_of_branch_sales_account:
			self.cost_of_branch_sales_account = heads["cost_of_branch_sales_account"]
		if heads.get("branch_sales_clearing_account") and not self.branch_sales_clearing_account:
			self.branch_sales_clearing_account = heads["branch_sales_clearing_account"]
		if heads.get("from_company_receivable_account") and not self.from_company_receivable_account:
			self.from_company_receivable_account = heads["from_company_receivable_account"]
		if heads.get("to_company_payable_account") and not self.to_company_payable_account:
			self.to_company_payable_account = heads["to_company_payable_account"]
		if heads.get("unrealized_branch_margin_account") and not self.unrealized_branch_margin_account:
			self.unrealized_branch_margin_account = heads["unrealized_branch_margin_account"]

	def on_cancel(self):
		errors = []
		for fieldname, doctype in (
			("issue_stock_entry", "Stock Entry"),
			("receipt_stock_entry", "Stock Entry"),
			("receivable_journal_entry", "Journal Entry"),
		):
			name = self.get(fieldname)
			if not name:
				continue
			try:
				doc = frappe.get_doc(doctype, name)
				if doc.docstatus == 1:
					doc.cancel()
			except Exception as e:
				errors.append(f"{doctype} {name}: {e!s}")
				frappe.log_error(
					title=_("Failed to cancel linked document {0} for Inter Company Transfer {1}").format(
						name, self.name
					),
					message=frappe.get_traceback(),
				)
		if errors:
			frappe.throw(
				_("Could not cancel all linked entries. Fix manually:\n{0}").format("\n".join(errors))
			)


