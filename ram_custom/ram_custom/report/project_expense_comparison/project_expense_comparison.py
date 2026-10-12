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
	data = get_data(gl_rows, projects, filters.company)
	chart = get_chart_data(data, projects)
	report_summary = get_report_summary(data)

	return columns, data, None, chart, report_summary


def get_gl_data(filters):
	gle = qb.DocType("GL Entry")
	acc = qb.DocType("Account")

	query = (
		qb.from_(gle)
		.join(acc)
		.on(gle.account == acc.name)
		.select(
			gle.account,
			acc.account_name,
			gle.project,
			(Sum(gle.debit) - Sum(gle.credit)).as_("amount"),
		)
		.where(acc.root_type == "Expense")
		.where(acc.is_group == 0)
		.where(gle.is_cancelled == 0)
		.where(gle.is_opening == "No")
		.where(gle.company == filters.company)
		.where(gle.project.isnotnull())
		.where(gle.project != "")
		.groupby(gle.account, gle.project)
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
			"label": _("Expense Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 220,
		}
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


def get_data(gl_rows, projects, company):
	if not projects:
		return []

	currency = frappe.get_cached_value("Company", company, "default_currency")

	accounts = {}
	for row in gl_rows:
		accounts.setdefault(
			row.account, {"account": row.account, "account_name": row.account_name, "amounts": {}}
		)
		accounts[row.account]["amounts"][row.project] = flt(row.amount)

	data = []
	for account in accounts.values():
		row = {"account": account["account"], "currency": currency}
		total = 0
		for project in projects:
			amount = flt(account["amounts"].get(project["name"]))
			row[project["fieldname"]] = amount
			total += amount
		row["total"] = total
		data.append(row)

	data.sort(key=lambda r: r["account"])
	return data


def get_chart_data(data, projects):
	if not data or not projects:
		return None

	labels = [p["label"] for p in projects]
	totals = []
	for project in projects:
		totals.append(sum(flt(row.get(project["fieldname"])) for row in data))

	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Total Expense"), "values": totals}],
		},
		"type": "bar",
		"colors": ["#fc4f51"],
	}


def get_report_summary(data):
	if not data:
		return None

	grand_total = sum(flt(row.get("total")) for row in data)

	return [
		{
			"value": grand_total,
			"indicator": "Blue",
			"label": _("Total Expense"),
			"datatype": "Currency",
		},
	]
