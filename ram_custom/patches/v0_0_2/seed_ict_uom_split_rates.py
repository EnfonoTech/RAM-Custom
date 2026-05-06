# Backfill the new UOM-split rate fields on Inter Company Transfer Item.
# Legacy rows stored cost_rate as a per-stock-UOM value (and transfer_rate was
# also treated that way during calculation). After the UOM-split fix, the
# stock-UOM rate lives in cost_rate_stock_uom and the selected-UOM rate lives
# in cost_rate. For legacy data the safest carry-over is:
#   cost_rate_stock_uom <- cost_rate           (preserves prior intent)
#   transfer_rate_stock_uom <- transfer_rate / cf  (matches old math)
#   stock_qty <- qty * cf
# We do not rewrite cost_rate / transfer_rate so submitted documents continue
# to display their original recorded values.

import frappe


def execute():
	if not frappe.db.has_column("Inter Company Transfer Item", "cost_rate_stock_uom"):
		return
	frappe.db.sql(
		"""
		update `tabInter Company Transfer Item`
		set
			cost_rate_stock_uom = case
				when ifnull(cost_rate_stock_uom, 0) = 0 then ifnull(cost_rate, 0)
				else cost_rate_stock_uom
			end,
			transfer_rate_stock_uom = case
				when ifnull(transfer_rate_stock_uom, 0) = 0 and ifnull(conversion_factor, 0) > 0
					then ifnull(transfer_rate, 0) / conversion_factor
				else transfer_rate_stock_uom
			end,
			stock_qty = case
				when ifnull(stock_qty, 0) = 0
					then ifnull(qty, 0) * ifnull(conversion_factor, 1)
				else stock_qty
			end
		where parenttype = 'Inter Company Transfer'
		"""
	)
