// Customer/Supplier quick entry:
// - VAT Registration Number sits with the other Customer identifiers, mandatory for
//   Customer Type = Company (the Client Script that enforces it only runs on the full
//   form; a Quick Entry dialog never fires Client Scripts, so the rule is repeated here).
// - "Primary Contact Details" stays its own collapsible section (Name, Mobile - optional).
// - "Primary Address Details" stays always expanded, reordered to match the
//   agreed sketch: Short Address/Building No, Street/District, City/Postal Code, Country.
frappe.provide("frappe.ui.form");

$(document).ready(function () {
	if (!frappe.ui.form.ContactAddressQuickEntryForm) return;

	frappe.ui.form.ContactAddressQuickEntryForm.prototype.get_variant_fields = function () {
		return [
			{
				// Deliberately NOT named custom_vat_registration_number: Layout
				// attach_doc_and_docfields() replaces a dialog df with the doctype's own
				// docfield whenever the fieldname exists in the meta, which would throw
				// away depends_on / mandatory_depends_on / description. The value is
				// copied onto the real fieldname in insert() below - the same aliasing
				// erpnext uses for email_address / mobile_number.
				label: __("VAT Registration Number"),
				fieldname: "vat_registration_number",
				fieldtype: "Data",
				// Supplier has no such field - this prototype is shared by both dialogs.
				depends_on: "eval:doc.doctype=='Customer'",
				mandatory_depends_on: "eval:doc.customer_type=='Company'",
				description: __("15 digits, as registered with ZATCA"),
			},
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
				// || doc.address_line1: erpnext creates the Address as soon as address_line1
				// is filled, and City/Country/Postal Code are mandatory on Address, so an
				// Individual entering an address must supply them too or the save rolls back.
				mandatory_depends_on:
					"eval:doc.customer_type=='Company' || doc.supplier_type=='Company' || doc.address_line1",
			},
			{
				label: __("Country"),
				fieldname: "country",
				fieldtype: "Link",
				options: "Country",
				mandatory_depends_on:
					"eval:doc.customer_type=='Company' || doc.supplier_type=='Company' || doc.address_line1",
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
				mandatory_depends_on:
					"eval:doc.customer_type=='Company' || doc.supplier_type=='Company' || doc.address_line1",
			},
			{
				label: __("Customer POS Id"),
				fieldname: "customer_pos_id",
				fieldtype: "Data",
				hidden: 1,
			},
		];
	};

	// Mirror of the "Customer type company vat reg no mandatory" Client Script, which the
	// dialog never runs: strip non-digits, then refuse to save a Company customer whose VAT
	// number is not exactly 15 digits.
	if (!frappe.ui.form.ContactAddressQuickEntryForm.prototype.__ram_vat_insert_patched) {
		const original_insert = frappe.ui.form.ContactAddressQuickEntryForm.prototype.insert;

		frappe.ui.form.ContactAddressQuickEntryForm.prototype.insert = function () {
			if (this.doctype !== "Customer") {
				return original_insert.call(this);
			}

			const values = this.dialog.get_values(true) || {};
			const entered = (values.vat_registration_number || "").toString();
			const digits = entered.replace(/\D/g, "");

			if (values.customer_type !== "Company") {
				// Individual: carry whatever was typed, if anything, and get out of the way.
				this.dialog.doc.custom_vat_registration_number = digits || "";
				return original_insert.call(this);
			}

			if (!/^\d{15}$/.test(digits)) {
				// register_primary_action() has already locked the dialog - release it,
				// otherwise the Save button stays dead and the user is stuck.
				this.dialog.working = false;
				this.dialog.clear_message();
				frappe.msgprint({
					title: __("Invalid VAT Registration Number"),
					indicator: "red",
					message: __("VAT Registration Number must be exactly 15 digits."),
				});
				return Promise.resolve();
			}

			// Stamp the real Customer fieldname; update_doc() only copies dialog
			// fieldnames, so this value survives to frappe.client.save untouched.
			this.dialog.doc.custom_vat_registration_number = digits;

			if (digits === entered) {
				return original_insert.call(this);
			}

			return Promise.resolve(
				this.dialog.set_value("vat_registration_number", digits)
			).then(() => original_insert.call(this));
		};

		frappe.ui.form.ContactAddressQuickEntryForm.prototype.__ram_vat_insert_patched = true;
	}
});
