// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.provide("ram_custom.reports");

ram_custom.reports.open_general_ledger = function (data, project) {
	if (!data || !data.account || !project) {
		return;
	}

	frappe.route_options = {
		company: frappe.query_report.get_filter_value("company"),
		account: data.account,
		project: project,
		from_date: frappe.query_report.get_filter_value("from_date"),
		to_date: frappe.query_report.get_filter_value("to_date"),
	};
	frappe.set_route("query-report", "General Ledger");
};

frappe.query_reports["Project Expense Comparison"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "projects",
			label: __("Projects"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Project", txt);
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: { company: company } };
			},
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// only the per-project amount columns carry `project`; skip zero/empty cells
		if (data && column.project && data[column.fieldname]) {
			const onclick = (
				"ram_custom.reports.open_general_ledger(" +
				JSON.stringify(data) +
				", " +
				JSON.stringify(column.project) +
				"); return false;"
			).replace(/"/g, "&quot;");

			value = `<a href="#" onclick="${onclick}">${value}</a>`;
		}

		return value;
	},
};
