# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from ram_custom.ram_custom.report.invoices_awaiting_receipt.invoices_awaiting_receipt import (
	VIEWS,
	execute,
	find_duplicates,
	invoice_root,
	match_documents,
	normalise,
)

SUP = "MADAR"


def pi(name, bill_no, supplier=SUP, linked=()):
	return {"name": name, "supplier": supplier, "bill_no": bill_no, "linked_receipts": set(linked)}


def pr(name, inv, supplier=SUP, inv_date=None):
	return {"name": name, "supplier": supplier, "inv": inv, "inv_date": inv_date}


class TestMatching(FrappeTestCase):
	"""Pure logic: no database rows needed."""

	def test_normalise_ignores_case_space_and_dashes(self):
		self.assertEqual(normalise(" in-01 533379 "), "IN01533379")
		self.assertEqual(normalise(None), "")

	def test_invoice_root_strips_duplicate_markers(self):
		self.assertEqual(invoice_root("IN01-533379-DUPLICTE"), "IN01533379")
		self.assertEqual(invoice_root("IN01-533379 copy2"), "IN01533379")
		self.assertEqual(invoice_root("IN01-533379"), "IN01533379")
		self.assertEqual(invoice_root("DUP"), "DUP")

	def test_pairs_on_supplier_and_number(self):
		by_number, matched_pi, matched_pr = match_documents(
			[pi("PI-1", "A/1"), pi("PI-2", "B2")], [pr("PR-1", "a-1"), pr("PR-9", "ZZ")]
		)
		self.assertEqual(by_number, {"PI-1": ["PR-1"]})
		self.assertEqual(matched_pi, {"PI-1"})
		self.assertEqual(matched_pr, {"PR-1"})

	def test_same_number_other_supplier_does_not_match(self):
		by_number, matched_pi, _pr = match_documents([pi("PI-1", "A1")], [pr("PR-1", "A1", supplier="OTHER")])
		self.assertFalse(by_number)
		self.assertFalse(matched_pi)

	def test_blank_numbers_never_match(self):
		by_number, matched_pi, matched_pr = match_documents([pi("PI-1", "")], [pr("PR-1", "")])
		self.assertFalse(by_number or matched_pi or matched_pr)

	def test_direct_link_counts_only_if_receipt_is_live(self):
		_b, matched_pi, matched_pr = match_documents([pi("PI-1", "X", linked=["PR-1"])], [pr("PR-1", "Y")])
		self.assertEqual((matched_pi, matched_pr), ({"PI-1"}, {"PR-1"}))
		_b, matched_pi, _m = match_documents([pi("PI-1", "X", linked=["PR-CANCELLED"])], [pr("PR-1", "Y")])
		self.assertFalse(matched_pi)

	def test_one_invoice_pairs_with_several_receipts(self):
		by_number, _a, _b = match_documents([pi("PI-1", "A1")], [pr("PR-1", "A1"), pr("PR-2", "a 1")])
		self.assertEqual(sorted(by_number["PI-1"]), ["PR-1", "PR-2"])


class TestDuplicates(FrappeTestCase):
	def test_duplicate_suffix_is_caught(self):
		"""The real case: IN01-533379 entered again as IN01-533379-DUPLICTE."""
		found = find_duplicates(
			[pr("PR-0192", "IN01-533379"), pr("PR-0411", "IN01-533379-DUPLICTE")],
			{},
		)
		self.assertEqual(found["PR-0192"]["related"], ["PR-0411"])
		self.assertEqual(found["PR-0411"]["related"], ["PR-0192"])

	def test_same_lines_and_invoice_date_is_caught_even_with_different_number(self):
		sig = (("ITEM", 7.0, 50.0),)
		found = find_duplicates(
			[pr("PR-1", "AAA", inv_date="2026-01-14"), pr("PR-2", "BBB", inv_date="2026-01-14")],
			{"PR-1": sig, "PR-2": sig},
		)
		self.assertEqual(set(found), {"PR-1", "PR-2"})

	def test_same_lines_different_invoice_date_is_not_flagged(self):
		sig = (("ITEM", 7.0, 50.0),)
		found = find_duplicates(
			[pr("PR-1", "AAA", inv_date="2026-01-14"), pr("PR-2", "BBB", inv_date="2026-02-14")],
			{"PR-1": sig, "PR-2": sig},
		)
		self.assertFalse(found)

	def test_different_suppliers_are_not_duplicates(self):
		found = find_duplicates([pr("PR-1", "A1"), pr("PR-2", "A1-DUP", supplier="OTHER")], {})
		self.assertFalse(found)

	def test_unique_numbers_are_not_flagged(self):
		self.assertFalse(find_duplicates([pr("PR-1", "A1"), pr("PR-2", "A2")], {}))


class TestReportOnSiteData(FrappeTestCase):
	"""Smoke and consistency checks against whatever data the site holds."""

	def _company(self):
		return frappe.db.get_value("Purchase Receipt", {"docstatus": 1}, "company")

	def test_every_view_runs(self):
		company = self._company()
		if not company or not frappe.db.has_column("Purchase Receipt", "custom_supplier_invoice_number"):
			self.skipTest("needs submitted Purchase Receipts with the supplier invoice field")
		for view in VIEWS:
			columns, data = execute({"company": company, "view": view})
			self.assertTrue(columns)
			fields = {c["fieldname"] for c in columns}
			for row in data:
				self.assertTrue(set(row) <= fields, f"{view}: row keys outside columns")

	def test_awaiting_and_no_invoice_never_list_a_matched_document(self):
		company = self._company()
		if not company or not frappe.db.has_column("Purchase Receipt", "custom_supplier_invoice_number"):
			self.skipTest("needs submitted Purchase Receipts with the supplier invoice field")
		_c, waiting = execute({"company": company, "view": "Invoices Awaiting Receipt"})
		for row in waiting:
			bill_no = frappe.db.get_value("Purchase Invoice", row["purchase_invoice"], "bill_no")
			supplier = row["supplier"]
			hits = [
				r.name
				for r in frappe.get_all(
					"Purchase Receipt",
					filters={"docstatus": 1, "is_return": 0, "supplier": supplier},
					fields=["name", "custom_supplier_invoice_number as inv"],
				)
				if normalise(r.inv) and normalise(r.inv) == normalise(bill_no)
			]
			self.assertFalse(hits, f"{row['purchase_invoice']} listed as waiting but {hits} match its number")

	def test_unknown_view_is_rejected(self):
		company = self._company()
		if not company:
			self.skipTest("no company data")
		with self.assertRaises(frappe.ValidationError):
			execute({"company": company, "view": "Nonsense"})

	def test_company_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			execute({"view": "Invoices Awaiting Receipt"})
