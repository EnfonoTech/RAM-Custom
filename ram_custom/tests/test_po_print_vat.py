# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPurchaseOrderPrintVat(FrappeTestCase):
	"""The PO print follows the document's own tax rate, not a hard-coded 15%."""

	FORMAT = "Purchase order new format"

	def _po(self, zero_rated):
		rate_filter = ["=", 0] if zero_rated else [">", 0]
		rows = frappe.get_all(
			"Purchase Taxes and Charges",
			filters={"parenttype": "Purchase Order", "charge_type": "On Net Total", "rate": rate_filter, "docstatus": ["<", 2]},
			fields=["parent"],
			limit=1,
		)
		return rows[0].parent if rows else None

	def _html(self, po):
		if not frappe.db.exists("Print Format", self.FORMAT):
			self.skipTest(f"{self.FORMAT} is not installed on this site")
		return frappe.get_print("Purchase Order", po, print_format=self.FORMAT)

	def test_no_hardcoded_rate_left(self):
		html = frappe.db.get_value("Print Format", self.FORMAT, "html") or ""
		self.assertNotIn("* 0.15", html)
		self.assertNotIn('<td class="text-center">15%</td>', html)

	def test_zero_rated_order_prints_zero(self):
		po = self._po(zero_rated=True)
		if not po:
			self.skipTest("no zero-rated Purchase Order")
		html = self._html(po)
		self.assertIn("0%", html)
		self.assertNotIn("15%", html)

	def test_standard_rated_order_still_prints_fifteen(self):
		po = self._po(zero_rated=False)
		if not po:
			self.skipTest("no standard-rated Purchase Order")
		rate = frappe.db.get_value(
			"Purchase Taxes and Charges", {"parent": po, "charge_type": "On Net Total"}, "rate"
		)
		self.assertIn(f"{rate:g}%", self._html(po))
