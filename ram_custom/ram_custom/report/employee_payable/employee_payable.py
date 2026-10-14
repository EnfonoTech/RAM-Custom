# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""Employee Payable: what was accrued, what was paid, what is still owed.

Payroll accrual entries post to the company's payroll payable account with the
Employee as party (HR Settings: process payroll accounting entry based on
employee). Salary payments post a debit to the same account and party. So per
employee, over a period:

    Opening  = credit - debit before From Date
    Accrued  = credit in the period
    Paid     = debit in the period
    Balance  = Opening + Accrued - Paid     (positive = still to be paid)

Only entries carrying an Employee party on the chosen account are read. Salary
posted straight to a separate per-staff ledger (no party) is not part of this
report.
"""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate

PRECISION = 2


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	account = get_account(filters)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return get_columns(currency), get_data(filters, account)


def validate_filters(filters):
	if not filters.company:
		frappe.throw(_("Please select a Company"))
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("From Date and To Date are mandatory"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))


def get_account(filters):
	account = filters.get("account") or frappe.get_cached_value(
		"Company", filters.company, "default_payroll_payable_account"
	)
	if not account:
		frappe.throw(
			_("Set a Payroll Payable Account in the filters, or a Default Payroll Payable Account on {0}").format(
				frappe.bold(filters.company)
			)
		)
	if frappe.get_cached_value("Account", account, "company") != filters.company:
		frappe.throw(_("Account {0} does not belong to {1}").format(frappe.bold(account), frappe.bold(filters.company)))
	return account


def get_columns(currency):
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 220},
		{"label": _("Opening"), "fieldname": "opening", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Accrued"), "fieldname": "accrued", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Paid"), "fieldname": "paid", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "options": currency, "width": 130},
	]


def get_data(filters, account):
	gle = frappe.qb.DocType("GL Entry")
	in_period = gle.posting_date >= getdate(filters.from_date)
	before = gle.posting_date < getdate(filters.from_date)

	query = (
		frappe.qb.from_(gle)
		.select(
			gle.party.as_("employee"),
			Sum(Case().when(before, gle.credit - gle.debit).else_(0)).as_("opening"),
			Sum(Case().when(in_period, gle.credit).else_(0)).as_("accrued"),
			Sum(Case().when(in_period, gle.debit).else_(0)).as_("paid"),
		)
		.where(gle.company == filters.company)
		.where(gle.account == account)
		.where(gle.party_type == "Employee")
		.where(gle.is_cancelled == 0)
		.where(gle.posting_date <= getdate(filters.to_date))
		.groupby(gle.party)
		.orderby(gle.party)
	)
	if filters.get("employee"):
		query = query.where(gle.party == filters.employee)

	rows = query.run(as_dict=True)
	names = get_employee_names([r.employee for r in rows])

	data = []
	for r in rows:
		opening, accrued, paid = (flt(r[k], PRECISION) for k in ("opening", "accrued", "paid"))
		balance = flt(opening + accrued - paid, PRECISION)
		if not (opening or accrued or paid or balance):
			continue
		if filters.get("hide_settled") and not balance:
			continue
		data.append(
			{
				"employee": r.employee,
				"employee_name": names.get(r.employee) or "",
				"opening": opening,
				"accrued": accrued,
				"paid": paid,
				"balance": balance,
			}
		)
	return data


def get_employee_names(employees):
	employees = [e for e in set(employees) if e]
	if not employees:
		return {}
	return {
		d.name: d.employee_name
		for d in frappe.get_all(
			"Employee", filters={"name": ["in", employees]}, fields=["name", "employee_name"]
		)
	}
