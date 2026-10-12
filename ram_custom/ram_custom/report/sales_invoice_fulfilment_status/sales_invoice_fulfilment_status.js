// Copyright (c) 2026, ramees and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Invoice Fulfilment Status"] = {
	"filters": [
		{"fieldname": "company", "label": __("Company"), "fieldtype": "Link", "options": "Company",
			"default": frappe.defaults.get_user_default("Company")},
		{"fieldname": "customer", "label": __("Customer"), "fieldtype": "Link", "options": "Customer"},
		{"fieldname": "from_date", "label": __("From Date"), "fieldtype": "Date"},
		{"fieldname": "to_date", "label": __("To Date"), "fieldtype": "Date"},
		{"fieldname": "fulfilment_status", "label": __("Fulfilment Status"), "fieldtype": "Select",
			"options": ["", "Fully Delivered", "Partially Delivered", "Not Delivered", "Stock Updated",
				"Return Unmatched", "Fully Reversed", "Delivery Returned, Invoice Open",
				"Partially Reversed"].join("\n")},
		{"fieldname": "show_returns", "label": __("Show Returns"), "fieldtype": "Select",
			"options": ["Both", "Yes", "No"].join("\n"), "default": "Both"}
	]
};
