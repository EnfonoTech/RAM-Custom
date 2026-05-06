frappe.query_reports["Inter-Company Cost Variance"] = {
	filters: [
		{
			fieldname: "from_company",
			label: __("From Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "to_company",
			label: __("To Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "inter_company_transfer",
			label: __("Inter Company Transfer"),
			fieldtype: "Link",
			options: "Inter Company Transfer",
		},
		{
			fieldname: "variance_threshold",
			label: __("Variance Threshold"),
			fieldtype: "Float",
			default: 0.01,
		},
		{
			fieldname: "show_zero_variance",
			label: __("Show Zero Variance Rows"),
			fieldtype: "Check",
			default: 0,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const out = default_formatter(value, row, column, data);
		if (column.fieldname === "variance" && data && flt(data.variance) !== 0) {
			const colour = flt(data.variance) > 0 ? "red" : "green";
			return `<span style="color:${colour}">${out}</span>`;
		}
		return out;
	},
	onload(report) {
		report.page.add_inner_button(__("Reconcile Variance"), () => {
			const filters = report.get_values() || {};
			frappe.new_doc("Inter Company Cost Variance Reconciliation", {
				from_company: filters.from_company || "",
				to_company: filters.to_company || "",
				period_from: filters.from_date || "",
				period_to: filters.to_date || "",
			});
		});
	},
};
