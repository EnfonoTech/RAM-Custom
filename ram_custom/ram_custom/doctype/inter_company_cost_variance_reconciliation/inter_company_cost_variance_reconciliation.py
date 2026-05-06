# Copyright (c) 2026, ramees and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from ram_custom.api.inter_company_transfer import (
	_get_company_pair_account_row,
	_get_historical_valuation_rate,
)

RECON_TAG = "ICT_VARIANCE_RECON"


def _marker(recon_id: str) -> str:
	return f"[{RECON_TAG}:{recon_id}]"


class InterCompanyCostVarianceReconciliation(Document):
	def validate(self):
		if self.from_company == self.to_company:
			frappe.throw(_("From Company and To Company cannot be the same"))
		if getdate(self.period_from) > getdate(self.period_to):
			frappe.throw(_("Period From cannot be after Period To"))
		self._fetch_accounts_from_settings()
		self._dedupe_rows()
		self._compute_totals()

	def before_submit(self):
		# Re-snapshot current SLE cost so we post against the latest figure,
		# not whatever was fetched into the form earlier.
		self._refresh_current_costs()
		self._compute_totals()
		if not self.items:
			frappe.throw(_("No variance rows to reconcile"))
		if abs(flt(self.total_variance)) < 0.01:
			frappe.throw(_("Total variance is zero — nothing to reconcile"))

	def on_submit(self):
		je_name = self._post_adjustment_journal_entry()
		self.db_set("journal_entry", je_name)
		self._update_ict_baselines()

	def on_cancel(self):
		# Restore baselines first so users see the correct variance again,
		# then cancel the JE last (failure here is non-fatal — log).
		self._restore_ict_baselines()
		if self.journal_entry:
			try:
				je = frappe.get_doc("Journal Entry", self.journal_entry)
				if je.docstatus == 1:
					je.cancel()
			except Exception:
				frappe.log_error(
					title=_("Failed to cancel reconciliation JE {0}").format(self.journal_entry),
					message=frappe.get_traceback(),
				)

	# ------------------------------------------------------------------
	# Internals
	# ------------------------------------------------------------------

	def _fetch_accounts_from_settings(self):
		if self.branch_sales_clearing_account and self.unrealized_branch_margin_account:
			return
		row = _get_company_pair_account_row(self.from_company, self.to_company)
		if not row:
			return
		if not self.branch_sales_clearing_account:
			self.branch_sales_clearing_account = row.get("branch_sales_clearing_account")
		if not self.unrealized_branch_margin_account:
			self.unrealized_branch_margin_account = row.get("unrealized_branch_margin_account")

	def _dedupe_rows(self):
		seen = set()
		deduped = []
		for row in self.items or []:
			key = (row.inter_company_transfer, row.ict_item_row)
			if not key[0] or not key[1] or key in seen:
				continue
			seen.add(key)
			deduped.append(row)
		self.items = deduped
		for idx, row in enumerate(self.items, start=1):
			row.idx = idx

	def _refresh_current_costs(self):
		for row in self.items:
			ict = frappe.db.get_value(
				"Inter Company Transfer",
				row.inter_company_transfer,
				["posting_date", "posting_time"],
				as_dict=True,
			)
			if not ict:
				frappe.throw(
					_("Inter Company Transfer {0} not found").format(row.inter_company_transfer)
				)
			child = frappe.db.get_value(
				"Inter Company Transfer Item",
				row.ict_item_row,
				[
					"item_code",
					"source_warehouse",
					"qty",
					"conversion_factor",
					"reconciled_cost_value",
				],
				as_dict=True,
			)
			if not child:
				frappe.throw(
					_("Inter Company Transfer row {0} no longer exists").format(row.ict_item_row)
				)
			rate = _get_historical_valuation_rate(
				child.item_code,
				child.source_warehouse,
				str(ict.posting_date) if ict.posting_date else None,
				ict.posting_time,
			)
			stock_qty = flt(child.qty) * flt(child.conversion_factor or 1)
			row.item_code = child.item_code
			row.source_warehouse = child.source_warehouse
			row.qty = child.qty
			row.stock_qty = stock_qty
			row.previous_baseline = flt(child.reconciled_cost_value, 2)
			row.current_sle_cost = flt(stock_qty * flt(rate), 2)
			row.variance = flt(row.current_sle_cost - row.previous_baseline, 2)

	def _compute_totals(self):
		total = 0.0
		for row in self.items or []:
			total += flt(row.variance)
		self.total_variance = flt(total, 2)

	def _post_adjustment_journal_entry(self) -> str:
		marker = _marker(self.name)
		if frappe.db.exists("Journal Entry", {"user_remark": ["like", f"%{marker}%"]}):
			frappe.throw(_("A Journal Entry already exists for this reconciliation"))

		variance = flt(self.total_variance, 2)
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.from_company
		je.posting_date = self.posting_date
		je.user_remark = (
			f"{marker} Inter-company cost variance reconciliation "
			f"{self.from_company} -> {self.to_company} "
			f"({self.period_from} to {self.period_to})"
		)
		if variance > 0:
			# Cost rose post-submit: original margin overstated. Reduce margin, credit clearing.
			je.append(
				"accounts",
				{
					"account": self.unrealized_branch_margin_account,
					"debit_in_account_currency": variance,
				},
			)
			je.append(
				"accounts",
				{
					"account": self.branch_sales_clearing_account,
					"credit_in_account_currency": variance,
				},
			)
		else:
			# Cost fell post-submit: original margin understated. Increase margin, debit clearing.
			amt = abs(variance)
			je.append(
				"accounts",
				{
					"account": self.branch_sales_clearing_account,
					"debit_in_account_currency": amt,
				},
			)
			je.append(
				"accounts",
				{
					"account": self.unrealized_branch_margin_account,
					"credit_in_account_currency": amt,
				},
			)
		je.insert()
		je.submit()
		return je.name

	def _update_ict_baselines(self):
		for row in self.items:
			frappe.db.set_value(
				"Inter Company Transfer Item",
				row.ict_item_row,
				{
					"previous_reconciled_cost_value": row.previous_baseline,
					"reconciled_cost_value": row.current_sle_cost,
				},
				update_modified=False,
			)

	def _restore_ict_baselines(self):
		for row in self.items:
			# Only restore if the current baseline still matches what we set on submit.
			# If a later reconciliation has moved the baseline forward, leave it alone.
			current = frappe.db.get_value(
				"Inter Company Transfer Item", row.ict_item_row, "reconciled_cost_value"
			)
			if current is None:
				continue
			if abs(flt(current) - flt(row.current_sle_cost)) > 0.01:
				continue
			frappe.db.set_value(
				"Inter Company Transfer Item",
				row.ict_item_row,
				"reconciled_cost_value",
				row.previous_baseline,
				update_modified=False,
			)


# ----------------------------------------------------------------------
# Whitelisted helpers
# ----------------------------------------------------------------------


@frappe.whitelist()
def fetch_variance_rows(
	from_company: str,
	to_company: str,
	period_from: str,
	period_to: str,
) -> list[dict]:
	"""Return ICT child rows whose current SLE cost differs from their baseline."""
	if not (from_company and to_company and period_from and period_to):
		frappe.throw(_("All filters are required"))
	if from_company == to_company:
		frappe.throw(_("From Company and To Company cannot be the same"))

	icts = frappe.get_all(
		"Inter Company Transfer",
		filters={
			"docstatus": 1,
			"from_company": from_company,
			"to_company": to_company,
			"posting_date": ["between", [getdate(period_from), getdate(period_to)]],
		},
		fields=["name", "posting_date", "posting_time"],
	)
	if not icts:
		return []

	out: list[dict] = []
	for ict in icts:
		children = frappe.get_all(
			"Inter Company Transfer Item",
			filters={"parent": ict.name, "parenttype": "Inter Company Transfer"},
			fields=[
				"name",
				"item_code",
				"source_warehouse",
				"qty",
				"conversion_factor",
				"reconciled_cost_value",
			],
		)
		for child in children:
			rate = _get_historical_valuation_rate(
				child.item_code,
				child.source_warehouse,
				str(ict.posting_date) if ict.posting_date else None,
				ict.posting_time,
			)
			stock_qty = flt(child.qty) * flt(child.conversion_factor or 1)
			current_cost = flt(stock_qty * flt(rate), 2)
			previous = flt(child.reconciled_cost_value, 2)
			variance = flt(current_cost - previous, 2)
			if abs(variance) < 0.01:
				continue
			out.append(
				{
					"inter_company_transfer": ict.name,
					"ict_item_row": child.name,
					"item_code": child.item_code,
					"source_warehouse": child.source_warehouse,
					"qty": child.qty,
					"stock_qty": stock_qty,
					"previous_baseline": previous,
					"current_sle_cost": current_cost,
					"variance": variance,
				}
			)
	return out
