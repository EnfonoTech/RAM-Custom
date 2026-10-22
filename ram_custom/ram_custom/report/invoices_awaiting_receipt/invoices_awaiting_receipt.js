// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Invoices Awaiting Receipt"] = {
	filters: [
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: [
				"Invoices Awaiting Receipt",
				"Receipts Without Invoice",
				"Amount Mismatch",
				"Possible Duplicate Receipts",
			].join("\n"),
			default: "Invoices Awaiting Receipt",
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
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
			fieldname: "min_age_days",
			label: __("Waiting at least (days)"),
			fieldtype: "Int",
			default: 0,
			description: __("Awaiting Receipt / Receipts Without Invoice views only"),
		},
		{
			fieldname: "tolerance",
			label: __("Amount Tolerance"),
			fieldtype: "Float",
			default: 1,
			description: __("Totals closer than this count as equal"),
		},
	],
};
