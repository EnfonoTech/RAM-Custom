// Customer/Supplier quick entry:
// - "Primary Contact Details" stays its own collapsible section (Name, Mobile - optional).
// - "Primary Address Details" stays always expanded, reordered to match the
//   agreed sketch: Short Address/Building No, Street/District, City/Postal Code, Country.
frappe.provide("frappe.ui.form");

$(document).ready(function () {
	if (!frappe.ui.form.ContactAddressQuickEntryForm) return;

	frappe.ui.form.ContactAddressQuickEntryForm.prototype.get_variant_fields = function () {
		return [
			{
				fieldtype: "Section Break",
				label: __("Primary Contact Details"),
				collapsible: 1,
			},
			{
				label: __("Name"),
				fieldname: "map_to_first_name",
				fieldtype: "Data",
				depends_on: "eval:doc.customer_type=='Company' || doc.supplier_type=='Company'",
			},
			{
				label: __("Last Name"),
				fieldname: "map_to_last_name",
				fieldtype: "Data",
				depends_on: "eval:doc.customer_type=='Company' || doc.supplier_type=='Company'",
			},
			{
				fieldtype: "Column Break",
			},
			{
				label: __("Email Id"),
				fieldname: "email_address",
				fieldtype: "Data",
				options: "Email",
			},
			{
				label: __("Mobile Number"),
				fieldname: "mobile_number",
				fieldtype: "Data",
			},
			{
				fieldtype: "Section Break",
				label: __("Primary Address Details"),
				collapsible: 0,
			},
			{
				label: __("Short Address"),
				fieldname: "address_line1",
				fieldtype: "Data",
				mandatory_depends_on: "eval:doc.customer_type=='Company' || doc.supplier_type=='Company'",
			},
			{
				label: __("Street"),
				fieldname: "address_line2",
				fieldtype: "Data",
				mandatory_depends_on: "eval:doc.customer_type=='Company' || doc.supplier_type=='Company'",
			},
			{
				label: __("City"),
				fieldname: "city",
				fieldtype: "Data",
				mandatory_depends_on: "eval:doc.customer_type=='Company' || doc.supplier_type=='Company'",
			},
			{
				label: __("Country"),
				fieldname: "country",
				fieldtype: "Link",
				options: "Country",
				mandatory_depends_on: "eval:doc.customer_type=='Company' || doc.supplier_type=='Company'",
			},
			{
				fieldtype: "Column Break",
			},
			{
				label: __("Building Number"),
				fieldname: "custom_building_number",
				fieldtype: "Data",
				mandatory_depends_on: "eval:doc.customer_type=='Company' || doc.supplier_type=='Company'",
			},
			{
				label: __("District"),
				fieldname: "custom_area",
				fieldtype: "Data",
				mandatory_depends_on: "eval:doc.customer_type=='Company' || doc.supplier_type=='Company'",
			},
			{
				label: __("Postal Code"),
				fieldname: "pincode",
				fieldtype: "Data",
				mandatory_depends_on: "eval:doc.customer_type=='Company' || doc.supplier_type=='Company'",
			},
			{
				label: __("Customer POS Id"),
				fieldname: "customer_pos_id",
				fieldtype: "Data",
				hidden: 1,
			},
		];
	};
});
