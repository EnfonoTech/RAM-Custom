# Backfill reconciled_cost_value for Inter Company Transfer rows that
# pre-date the variance reconciliation feature. Without this seed, the
# Inter-Company Cost Variance report would report the full cost_value as
# variance for every legacy ICT.

import frappe


def execute():
	if not frappe.db.has_column("Inter Company Transfer Item", "reconciled_cost_value"):
		return
	frappe.db.sql(
		"""
		update `tabInter Company Transfer Item`
		set
			reconciled_cost_value = cost_value,
			previous_reconciled_cost_value = cost_value
		where parenttype = 'Inter Company Transfer'
			and (reconciled_cost_value is null or reconciled_cost_value = 0)
			and cost_value is not null
		"""
	)
