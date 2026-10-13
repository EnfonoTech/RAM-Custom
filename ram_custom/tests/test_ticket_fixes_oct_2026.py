# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.tests.utils import FrappeTestCase

from ram_custom.api.address_arabic import ARABIC_FIELD_PAIRS, sync_arabic_fields


class TestAddressArabicSync(FrappeTestCase):
	"""Ticket 3: the visible Arabic fields and the older duplicates stay identical."""

	def _address(self, **values):
		doc = frappe.new_doc("Address")
		doc.update(values)
		return doc

	def test_visible_value_is_mirrored_into_older_field(self):
		for visible, older in ARABIC_FIELD_PAIRS:
			doc = self._address(**{visible: "المحمدية"})
			sync_arabic_fields(doc)
			self.assertEqual(doc.get(older), "المحمدية", older)

	def test_older_only_value_is_copied_up(self):
		for visible, older in ARABIC_FIELD_PAIRS:
			doc = self._address(**{older: "الرياض"})
			sync_arabic_fields(doc)
			self.assertEqual(doc.get(visible), "الرياض", visible)

	def test_visible_wins_when_both_differ(self):
		visible, older = ARABIC_FIELD_PAIRS[0]
		doc = self._address(**{visible: "جديد", older: "قديم"})
		sync_arabic_fields(doc)
		self.assertEqual(doc.get(older), "جديد")

	def test_both_empty_stay_empty(self):
		doc = self._address()
		sync_arabic_fields(doc)
		for visible, older in ARABIC_FIELD_PAIRS:
			self.assertFalse(doc.get(visible))
			self.assertFalse(doc.get(older))

	def test_old_fields_hidden_and_phone_visible(self):
		meta = frappe.get_meta("Address")
		self.assertFalse(meta.get_field("phone").hidden, "phone must be visible")
		for _visible, older in ARABIC_FIELD_PAIRS:
			self.assertTrue(meta.get_field(older).hidden, f"{older} must be hidden")
		for visible, _older in ARABIC_FIELD_PAIRS:
			self.assertFalse(meta.get_field(visible).hidden, f"{visible} must be visible")


class TestDeliveryNoteReturnStatusPatch(FrappeTestCase):
	"""Ticket 5: old return Delivery Notes labelled 'To Bill' become 'Return'."""

	def test_patch_relabels_only_unbilled_returns(self):
		from ram_custom.patches.v0_0_3.fix_delivery_note_return_status import execute

		returns = frappe.get_all(
			"Delivery Note",
			filters={"docstatus": 1, "is_return": 1, "status": "Return", "per_billed": 0},
			fields=["name", "modified"],
			limit=1,
		)
		if not returns:
			self.skipTest("no submitted return Delivery Note in this database")

		name, modified = returns[0].name, returns[0].modified
		frappe.db.set_value("Delivery Note", name, "status", "To Bill", update_modified=False)

		# a normal (non-return) delivery that really is waiting to be billed must not change
		normal = frappe.get_all(
			"Delivery Note",
			filters={"docstatus": 1, "is_return": 0, "status": "To Bill", "per_billed": 0},
			pluck="name",
			limit=1,
		)
		if not normal:
			self.skipTest("no normal Delivery Note waiting to be billed in this database")

		execute()

		self.assertEqual(frappe.db.get_value("Delivery Note", name, "status"), "Return")
		self.assertEqual(frappe.db.get_value("Delivery Note", name, "modified"), modified)
		if normal:
			self.assertEqual(frappe.db.get_value("Delivery Note", normal[0], "status"), "To Bill")

		# idempotent: a second run changes nothing
		execute()
		self.assertEqual(frappe.db.get_value("Delivery Note", name, "status"), "Return")

	def test_returns_that_were_billed_are_left_alone(self):
		from ram_custom.patches.v0_0_3.fix_delivery_note_return_status import execute

		billed = frappe.get_all(
			"Delivery Note",
			filters={"docstatus": 1, "is_return": 1, "per_billed": [">", 0]},
			fields=["name", "status"],
			limit=1,
		)
		if not billed:
			self.skipTest("no billed return Delivery Note in this database")

		name = billed[0].name
		frappe.db.set_value("Delivery Note", name, "status", "To Bill", update_modified=False)
		execute()
		self.assertEqual(frappe.db.get_value("Delivery Note", name, "status"), "To Bill")
		frappe.db.set_value("Delivery Note", name, "status", billed[0].status, update_modified=False)

	def test_no_returns_left_showing_to_bill(self):
		from ram_custom.patches.v0_0_3.fix_delivery_note_return_status import execute

		normal_before = frappe.db.count(
			"Delivery Note", {"docstatus": 1, "is_return": 0, "status": "To Bill"}
		)
		execute()
		self.assertEqual(
			frappe.db.count("Delivery Note", {"docstatus": 1, "is_return": 0, "status": "To Bill"}),
			normal_before,
			"normal deliveries waiting to be billed must keep the 'To Bill' status",
		)
		leftovers = frappe.db.count(
			"Delivery Note",
			{"docstatus": 1, "is_return": 1, "per_billed": 0, "status": "To Bill"},
		)
		self.assertEqual(leftovers, 0)


class TestStockLedgerWithSupplierDetails(FrappeTestCase):
	"""Ticket 1: Supplier, Supplier Invoice No and Date columns on the Stock Ledger."""

	MODULE = (
		"ram_custom.ram_custom.report.stock_ledger_with_supplier_details.stock_ledger_with_supplier_details"
	)

	def test_columns_are_inserted_right_after_voucher_no(self):
		report = frappe.get_attr(f"{self.MODULE}.insert_supplier_columns")
		columns = [
			{"fieldname": "voucher_type"},
			{"fieldname": "voucher_no"},
			{"fieldname": "batch_no"},
		]
		report(columns)
		self.assertEqual(
			[c["fieldname"] for c in columns],
			[
				"voucher_type",
				"voucher_no",
				"supplier",
				"supplier_invoice_no",
				"supplier_invoice_date",
				"batch_no",
			],
		)

	def test_purchase_invoice_row_gets_supplier_details(self):
		add_supplier_details = frappe.get_attr(f"{self.MODULE}.add_supplier_details")
		pi = frappe.get_all(
			"Purchase Invoice",
			filters={"docstatus": 1, "bill_no": ["!=", ""]},
			fields=["name", "supplier", "bill_no", "bill_date"],
			limit=1,
		)
		if not pi:
			self.skipTest("no submitted Purchase Invoice with a supplier invoice number")

		row = frappe._dict(voucher_type="Purchase Invoice", voucher_no=pi[0].name)
		other = frappe._dict(voucher_type="Delivery Note", voucher_no="DN-NOT-A-PURCHASE")
		add_supplier_details([row, other])

		self.assertEqual(row.supplier, pi[0].supplier)
		self.assertEqual(row.supplier_invoice_no, pi[0].bill_no)
		self.assertEqual(row.supplier_invoice_date, pi[0].bill_date)
		self.assertIsNone(other.get("supplier"))

	def test_purchase_receipt_shows_the_invoice_typed_on_the_receipt(self):
		add_supplier_details = frappe.get_attr(f"{self.MODULE}.add_supplier_details")
		pr = frappe.get_all(
			"Purchase Receipt",
			filters={"docstatus": 1, "custom_supplier_invoice_number": ["!=", ""]},
			fields=["name", "supplier", "custom_supplier_invoice_number", "custom_supplier_invoice_date"],
			limit=1,
		)
		if not pr:
			self.skipTest("no submitted Purchase Receipt with a supplier invoice number")

		row = frappe._dict(voucher_type="Purchase Receipt", voucher_no=pr[0].name)
		add_supplier_details([row])
		self.assertEqual(row.supplier, pr[0].supplier)
		self.assertEqual(row.supplier_invoice_no, pr[0].custom_supplier_invoice_number)
		self.assertEqual(row.supplier_invoice_date, pr[0].custom_supplier_invoice_date)

	def test_receipt_without_an_invoice_number_falls_back_to_the_billing_invoice(self):
		add_supplier_details = frappe.get_attr(f"{self.MODULE}.add_supplier_details")
		link = frappe.db.sql(
			"""
			select pr.name as receipt, pi.bill_no, pi.bill_date
			from `tabPurchase Receipt` pr
			join `tabPurchase Invoice Item` pii on pii.purchase_receipt = pr.name
			join `tabPurchase Invoice` pi on pi.name = pii.parent
			where pr.docstatus = 1 and ifnull(pr.custom_supplier_invoice_number, '') = ''
				and pi.docstatus = 1 and ifnull(pi.bill_no, '') != ''
			limit 1
			""",
			as_dict=True,
		)
		if not link:
			self.skipTest("no un-numbered Purchase Receipt that was billed through a Purchase Invoice")

		row = frappe._dict(voucher_type="Purchase Receipt", voucher_no=link[0].receipt)
		add_supplier_details([row])
		self.assertEqual(row.supplier_invoice_no, link[0].bill_no)
		self.assertEqual(row.supplier_invoice_date, link[0].bill_date)

	def test_report_runs_and_keeps_standard_columns(self):
		execute = frappe.get_attr(f"{self.MODULE}.execute")
		company = frappe.db.get_value("Stock Ledger Entry", {"is_cancelled": 0}, "company")
		if not company:
			self.skipTest("no stock ledger entries")

		filters = frappe._dict(
			company=company,
			from_date=frappe.utils.add_months(frappe.utils.today(), -1),
			to_date=frappe.utils.today(),
			valuation_field_type="Currency",
		)
		columns, data = execute(filters)[:2]
		fieldnames = [c["fieldname"] for c in columns]
		self.assertIn("voucher_no", fieldnames)
		self.assertEqual(fieldnames.index("supplier"), fieldnames.index("voucher_no") + 1)
		self.assertIn("supplier_invoice_date", fieldnames)


class TestQuotationBilingualPrint(FrappeTestCase):
	"""Ticket 8: the Quotation print carries Arabic next to the English labels."""

	def _html(self):
		if not frappe.db.exists("Print Format", "Quotation Bilingual"):
			self.skipTest("print format 'Quotation Bilingual' is not installed on this site")
		name = frappe.db.get_value("Quotation", {"quotation_to": "Customer", "docstatus": ["<", 2]}, "name")
		if not name:
			self.skipTest("no Quotation in this database")
		return name, frappe.get_print("Quotation", name, print_format="Quotation Bilingual")

	def test_labels_are_bilingual(self):
		_name, html = self._html()
		for arabic in (
			"عرض سعر",
			"رقم العرض",
			"التاريخ",
			"رقم العميل",
			"المجموع الفرعي",
			"الإجمالي الكلي",
			"الشروط والأحكام",
		):
			self.assertIn(arabic, html, arabic)
		for english in ("QUOTATION", "Quotation No", "Sub Total", "Grand Total", "TERMS"):
			self.assertIn(english, html, english)

	def test_customer_arabic_name_and_id_are_printed(self):
		name, html = self._html()
		doc = frappe.get_doc("Quotation", name)
		self.assertRegex(
			html, rf"(?s)Customer ID.*?{re.escape(doc.party_name)}", "Customer ID must show party_name"
		)
		arabic = frappe.db.get_value("Customer", doc.party_name, "custom_customer_name_arabic")
		if arabic:
			self.assertIn(arabic, html)

	def test_item_arabic_name_is_printed_under_description(self):
		if not frappe.get_meta("Item").has_field("custom_item_name_arabic"):
			self.skipTest("Item has no custom_item_name_arabic field")
		row = frappe.db.sql(
			"""
			select qi.parent, qi.item_code, i.custom_item_name_arabic as arabic
			from `tabQuotation Item` qi
			join `tabQuotation` q on q.name = qi.parent
			join `tabItem` i on i.name = qi.item_code
			where q.docstatus < 2 and q.quotation_to = 'Customer'
			  and ifnull(i.custom_item_name_arabic, '') != ''
			limit 1
			""",
			as_dict=True,
		)
		if not row:
			self.skipTest("no Quotation line with an Arabic item name")
		html = frappe.get_print("Quotation", row[0].parent, print_format="Quotation Bilingual")
		self.assertIn(row[0].arabic, html)

	def test_current_default_format_is_untouched(self):
		default = frappe.db.get_value(
			"Property Setter", {"doc_type": "Quotation", "property": "default_print_format"}, "value"
		)
		self.assertNotEqual(default, "Quotation Bilingual", "the default must only change after sign-off")
