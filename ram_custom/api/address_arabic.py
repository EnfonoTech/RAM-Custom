import frappe

# (visible field, older field that print formats still read)
ARABIC_FIELD_PAIRS = (
	("custom_address_line1_arabic", "custom_address_line_1_arabic"),
	("custom_area_arabic", "custom_areadistrict_arabic"),
	("custom_city_arabic", "custom_citytown_arabic"),
)


def sync_arabic_fields(doc, method=None):
	"""Keep the two parallel sets of Arabic address fields identical.

	The form only shows the first field of each pair; print formats written
	earlier still read the second. Whatever the user (or the translate button /
	auto-translation) puts in the visible field is mirrored into the older one.
	If only the older field has text (legacy rows), it is copied up so nothing
	is lost on the next save.
	"""
	for visible, older in ARABIC_FIELD_PAIRS:
		if not (doc.meta.has_field(visible) and doc.meta.has_field(older)):
			continue

		visible_value = (doc.get(visible) or "").strip()
		older_value = (doc.get(older) or "").strip()

		if visible_value:
			doc.set(older, visible_value)
		elif older_value:
			doc.set(visible, older_value)
