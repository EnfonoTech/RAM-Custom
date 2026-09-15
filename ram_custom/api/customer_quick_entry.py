import frappe


def set_extra_address_fields(doc, method=None):
	"""The Customer quick entry dialog collects Building Number and District
	alongside the standard address fields, but core `make_address()` only
	persists the fixed set it knows about. Copy the extra values onto the
	primary address it just created."""
	building_number = doc.get("custom_building_number")
	district = doc.get("custom_area")
	if not (building_number or district):
		return

	address_name = frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": "Customer", "link_name": doc.name, "parenttype": "Address"},
		"parent",
	)
	if not address_name:
		return

	values = {}
	if building_number:
		values["custom_building_number"] = building_number
	if district:
		values["custom_area"] = district

	frappe.db.set_value("Address", address_name, values)
