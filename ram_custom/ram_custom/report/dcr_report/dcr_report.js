// Copyright (c) 2026, ramees and contributors
// For license information, please see license.txt

//Filters for DCR Report

frappe.query_reports["DCR Report"] = {
    "filters": [
        {
            "fieldname": "date",
            "label": "Date",
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 0 
        },
        {
            "fieldname": "type",
            "label": "Type",
            "fieldtype": "Select",
            "options": "\nCash Sales\nCard Sales\nCredit Sales\nCash Purchases\nCard Purchases\nCredit Purchases\nSales Return\nPurchase Return\nCustomer Receipts\nSupplier Payments\nBank Receipts\nBank Payments\nCash Receipts\nCash Payments\nJournal Entry\nInternal Transfer",
            "reqd": 0 
        },
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 0
        },
        {
            "fieldname": "cost_center",
            "label": "Cost Center",
            "fieldtype": "Link",
            "options": "Cost Center",
            "get_query": function() {
             var company = frappe.query_report.get_filter_value("company");
             if (company) {
                 return {
                     "filters": {
                         "company": company
                     }
                 };
             } else {
                 return {};
             }
}
       }
    ],

    // Types into a clickable link

    "formatter": function(value, row, column, data, default_formatter) {

        value = default_formatter(value, row, column, data);

        if (column.fieldname === "type" && data && data.voucher_type && data.voucher_no) {

            return `<a href="/app/${frappe.router.slug(data.voucher_type)}/${data.voucher_no}"
                    style="color:#000000; text-decoration:underline;">
                        ${value}
                    </a>`;
        }

        return value;
    }
};
