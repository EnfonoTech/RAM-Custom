// Copyright (c) 2026, ramees and contributors
// For license information, please see license.txt

frappe.query_reports["Purchase Invoice Fulfilment Status"] = {
	"filters": [
		{"fieldname": "company", "label": __("Company"), "fieldtype": "Link", "options": "Company",
			"default": frappe.defaults.get_user_default("Company")},
		{"fieldname": "supplier", "label": __("Supplier"), "fieldtype": "Link", "options": "Supplier"},
		{"fieldname": "from_date", "label": __("From Date"), "fieldtype": "Date"},
		{"fieldname": "to_date", "label": __("To Date"), "fieldtype": "Date"},
		{"fieldname": "fulfilment_status", "label": __("Fulfilment Status"), "fieldtype": "Select",
			"options": ["", "Fully Received", "Partially Received", "Not Received", "Stock Updated",
				"Return Unmatched", "Fully Reversed", "Receipt Returned, Invoice Open",
				"Partially Reversed"].join("\n")},
		{"fieldname": "show_returns", "label": __("Show Returns"), "fieldtype": "Select",
			"options": ["Both", "Yes", "No"].join("\n"), "default": "Both"}
	]
};
