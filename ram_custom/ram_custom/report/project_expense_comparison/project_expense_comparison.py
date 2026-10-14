# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _, qb
from frappe.query_builder import Order
from frappe.query_builder.functions import Sum
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))

	gl_rows = get_gl_data(filters)
	projects = get_projects(gl_rows, filters)
	columns = get_columns(projects)
	data = get_data(gl_rows, projects, filters.company, get_root_types(filters))
	chart = get_chart_data(data, projects)
	report_summary = get_report_summary(data)

	return columns, data, None, chart, report_summary


def get_root_types(filters):
	if filters.get("account_type") in ("Income", "Expense"):
		return [filters.account_type]
	return ["Income", "Expense"]


def get_gl_data(filters):
	gle = qb.DocType("GL Entry")
	acc = qb.DocType("Account")

	root_types = get_root_types(filters)

	query = (
		qb.from_(gle)
		.join(acc)
		.on(gle.account == acc.name)
		.select(
			gle.account,
			acc.account_name,
			acc.root_type,
			gle.project,
			(Sum(gle.debit) - Sum(gle.credit)).as_("amount"),
		)
		.where(acc.root_type.isin(root_types))
		.where(acc.is_group == 0)
		.where(gle.is_cancelled == 0)
		.where(gle.is_opening == "No")
		.where(gle.company == filters.company)
		.where(gle.project.isnotnull())
		.where(gle.project != "")
		.groupby(gle.account, gle.project, acc.root_type)
		.orderby(acc.name, Order.asc)
	)

	if filters.get("from_date"):
		query = query.where(gle.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(gle.posting_date <= filters.to_date)
	if filters.get("cost_center"):
		query = query.where(gle.cost_center == filters.cost_center)

	projects_filter = filters.get("projects")
	if projects_filter:
		if isinstance(projects_filter, str):
			projects_filter = frappe.parse_json(projects_filter)
		query = query.where(gle.project.isin(projects_filter))

	return query.run(as_dict=True)


def get_projects(gl_rows, filters):
	projects_filter = filters.get("projects")
	if projects_filter:
		if isinstance(projects_filter, str):
			projects_filter = frappe.parse_json(projects_filter)
		project_names = set(projects_filter)
	else:
		project_names = {row.project for row in gl_rows}

	if not project_names:
		return []

	project_labels = frappe.db.get_all(
		"Project",
		filters={"name": ["in", list(project_names)]},
		fields=["name", "project_name"],
		order_by="name asc",
	)

	return [
		{
			"name": p.name,
			"label": p.project_name or p.name,
			"fieldname": frappe.scrub(p.name),
		}
		for p in project_labels
	]


def get_columns(projects):
	columns = [
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 220,
		},
		{
			"fieldname": "root_type",
			"label": _("Account Type"),
			"fieldtype": "Data",
			"width": 110,
		},
	]

	for project in projects:
		columns.append(
			{
				"fieldname": project["fieldname"],
				"label": project["label"],
				"fieldtype": "Currency",
				"options": "currency",
				"width": 140,
				"project": project["name"],
			}
		)

	columns.append(
		{
			"fieldname": "total",
			"label": _("Total"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		}
	)
	columns.append(
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 90,
			"hidden": 1,
		}
	)

	return columns


def get_data(gl_rows, projects, company, root_types):
	if not projects:
		return []

	currency = frappe.get_cached_value("Company", company, "default_currency")

	accounts = {}
	for row in gl_rows:
		accounts.setdefault(
			row.account,
			{"account": row.account, "root_type": row.root_type, "amounts": {}},
		)
		# income is stored as credit; show it as a positive figure
		sign = -1 if row.root_type == "Income" else 1
		accounts[row.account]["amounts"][row.project] = sign * flt(row.amount)

	data = []
	totals = {}
	for root_type in root_types:
		section_total = {p["fieldname"]: 0 for p in projects}
		section_accounts = sorted(
			(a for a in accounts.values() if a["root_type"] == root_type), key=lambda a: a["account"]
		)
		for account in section_accounts:
			row = {"account": account["account"], "root_type": root_type, "currency": currency}
			for project in projects:
				amount = flt(account["amounts"].get(project["name"]))
				row[project["fieldname"]] = amount
				section_total[project["fieldname"]] += amount
			row["total"] = sum(row[p["fieldname"]] for p in projects)
			data.append(row)

		total_row = {"account": _("Total {0}").format(_(root_type)), "currency": currency, "bold": 1}
		total_row.update(section_total)
		total_row["total"] = sum(section_total.values())
		data.append(total_row)
		totals[root_type] = total_row

	if len(root_types) < 2:
		return data

	net = {"account": _("Net Profit / (Loss)"), "currency": currency, "bold": 1}
	for project in projects:
		fn = project["fieldname"]
		net[fn] = totals["Income"][fn] - totals["Expense"][fn]
	net["total"] = totals["Income"]["total"] - totals["Expense"]["total"]
	data.append(net)
	return data


def get_chart_data(data, projects):
	if not data or not projects:
		return None

	by_account = {row["account"]: row for row in data if row.get("bold")}
	income = by_account.get(_("Total Income"), {})
	expense = by_account.get(_("Total Expense"), {})

	datasets, colors = [], []
	if income:
		datasets.append({"name": _("Income"), "values": [flt(income.get(p["fieldname"])) for p in projects]})
		colors.append("#29cd42")
	if expense:
		datasets.append({"name": _("Expense"), "values": [flt(expense.get(p["fieldname"])) for p in projects]})
		colors.append("#fc4f51")

	return {
		"data": {
			"labels": [p["label"] for p in projects],
			"datasets": datasets,
		},
		"type": "bar",
		"colors": colors,
	}


def get_report_summary(data):
	if not data:
		return None

	by_account = {row["account"]: row for row in data if row.get("bold")}
	income = flt(by_account.get(_("Total Income"), {}).get("total"))
	expense = flt(by_account.get(_("Total Expense"), {}).get("total"))

	summary = []
	if _("Total Income") in by_account:
		summary.append(
			{"value": income, "indicator": "Green", "label": _("Total Income"), "datatype": "Currency"}
		)
	if _("Total Expense") in by_account:
		summary.append(
			{"value": expense, "indicator": "Red", "label": _("Total Expense"), "datatype": "Currency"}
		)
	if _("Net Profit / (Loss)") in by_account:
		summary.append(
			{
				"value": income - expense,
				"indicator": "Green" if income >= expense else "Red",
				"label": _("Net Profit / (Loss)"),
				"datatype": "Currency",
			}
		)
	return summary
