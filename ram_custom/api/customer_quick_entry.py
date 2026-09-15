import frappe


def set_extra_address_fields(doc, method=None):
	"""The Customer quick entry dialog collects Building Number and District
	alongside the standard address fields, but core `make_address()` only
	persists the fixed set it knows about. Copy the extra values onto the
	primary address it just created.

	Wired to `on_update`, not `after_insert`: `Document.insert()` runs
	`after_insert` (document.py:326) BEFORE `run_post_save_methods()`
	(document.py:334), and the Address is only created inside
	`Customer.on_update` -> `create_primary_address()`. On `after_insert`
	there is no Address and no Dynamic Link yet, so the values were silently
	dropped and the customer later failed ZATCA B2B validation with
	"Please set a building number for customer address."
	"""
	if not doc.flags.is_new_doc:
		return

	building_number = doc.get("custom_building_number")
	district = doc.get("custom_area")
	if not (building_number or district):
		return

	# create_primary_address() db_sets this, so it is populated in memory by now.
	address_name = doc.get("customer_primary_address")
	if not address_name:
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
