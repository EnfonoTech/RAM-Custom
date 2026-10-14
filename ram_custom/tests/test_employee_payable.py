# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from ram_custom.ram_custom.report.employee_payable.employee_payable import execute


class TestEmployeePayable(FrappeTestCase):
	"""The report must agree with the General Ledger, employee by employee."""

	def _account_with_employee_entries(self):
		row = frappe.db.sql(
			"""
			select company, account from `tabGL Entry`
			where party_type = 'Employee' and is_cancelled = 0
			group by company, account order by count(*) desc limit 1
			""",
			as_dict=True,
		)
		return row[0] if row else None

	def _filters(self, ctx, **extra):
		return {"company": ctx.company, "account": ctx.account, "from_date": "2000-01-01", "to_date": today(), **extra}

	def test_balance_matches_general_ledger(self):
		ctx = self._account_with_employee_entries()
		if not ctx:
			self.skipTest("no employee-party GL entries on this site")
		_cols, data = execute(self._filters(ctx))
		expected = {
			d.party: flt(d.bal, 2)
			for d in frappe.db.sql(
				"""
				select party, sum(credit - debit) bal from `tabGL Entry`
				where company = %s and account = %s and party_type = 'Employee' and is_cancelled = 0
				group by party
				""",
				(ctx.company, ctx.account),
				as_dict=True,
			)
		}
		for row in data:
			self.assertAlmostEqual(row["balance"], expected[row["employee"]], places=2)
			self.assertAlmostEqual(row["opening"] + row["accrued"] - row["paid"], row["balance"], places=2)

	def test_opening_moves_with_from_date(self):
		ctx = self._account_with_employee_entries()
		if not ctx:
			self.skipTest("no employee-party GL entries on this site")
		_c, all_time = execute(self._filters(ctx))
		_c, from_today = execute(self._filters(ctx, from_date=today()))
		by_emp = {r["employee"]: r for r in all_time}
		for r in from_today:
			self.assertAlmostEqual(r["opening"], by_emp[r["employee"]]["balance"] - r["accrued"] + r["paid"], places=2)

	def test_hide_settled_drops_only_zero_balances(self):
		ctx = self._account_with_employee_entries()
		if not ctx:
			self.skipTest("no employee-party GL entries on this site")
		_c, shown = execute(self._filters(ctx, hide_settled=1))
		self.assertTrue(all(r["balance"] for r in shown))

	def test_wrong_company_account_is_rejected(self):
		ctx = self._account_with_employee_entries()
		other = frappe.db.get_value("Company", {"name": ["!=", ctx.company if ctx else ""]}, "name")
		if not ctx or not other:
			self.skipTest("needs two companies")
		with self.assertRaises(frappe.ValidationError):
			execute({"company": other, "account": ctx.account, "from_date": "2026-01-01", "to_date": today()})

	def test_dates_are_validated(self):
		with self.assertRaises(frappe.ValidationError):
			execute({"company": "X", "from_date": "2026-02-01", "to_date": "2026-01-01"})
