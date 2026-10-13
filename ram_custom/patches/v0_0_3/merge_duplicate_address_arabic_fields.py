# Ticket 3: Address carries two parallel sets of Arabic fields.
#
#   shown going forward (arabic_translation app)   kept in sync (older, used by print formats)
#   custom_address_line1_arabic                    custom_address_line_1_arabic
#   custom_area_arabic                             custom_areadistrict_arabic
#   custom_city_arabic                             custom_citytown_arabic
#
# The older fields are still read by live print formats, so we do not delete
# them; they are hidden on the form (Property Setters in fixtures) and kept in
# step by `ram_custom.api.address_arabic.sync_arabic_fields`. This patch makes
# the two sets agree for existing rows: whichever side is empty is filled from
# the other. Rows where both sides hold *different* text are left untouched and
# listed in the log for a person to decide.

import frappe

PAIRS = (
	("custom_address_line1_arabic", "custom_address_line_1_arabic"),
	("custom_area_arabic", "custom_areadistrict_arabic"),
	("custom_city_arabic", "custom_citytown_arabic"),
)


def execute():
	address = frappe.qb.DocType("Address")
	log = frappe.logger("ram_custom")

	for new, old in PAIRS:
		if not (frappe.db.has_column("Address", new) and frappe.db.has_column("Address", old)):
			continue

		new_col, old_col = address[new], address[old]
		is_empty = lambda col: (col.isnull()) | (col == "")  # noqa: E731

		(frappe.qb.update(address).set(new_col, old_col).where(is_empty(new_col) & ~is_empty(old_col))).run()
		(frappe.qb.update(address).set(old_col, new_col).where(is_empty(old_col) & ~is_empty(new_col))).run()

		differing = (
			frappe.qb.from_(address)
			.select(address.name)
			.where(~is_empty(new_col) & ~is_empty(old_col) & (new_col != old_col))
		).run(pluck="name")
		if differing:
			log.warning(f"Address Arabic fields differ ({new} vs {old}): {differing}")
