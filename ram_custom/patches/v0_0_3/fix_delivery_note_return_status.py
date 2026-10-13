# Ticket 5: submitted return Delivery Notes created before ERPNext started
# stamping the "Return" status still show "To Bill" in the list view.
#
# ERPNext's own rule (status_updater.py, "Delivery Note") is:
#   Return = is_return == 1 and per_billed == 0 and docstatus == 1
# so this only brings old rows in line with that rule. Nothing is touched when
# per_billed > 0 (a credit note was actually raised) or when the user has
# already closed the document. `modified` is left alone so the lists don't
# reshuffle and nobody sees a phantom edit.

import frappe


def execute():
	dn = frappe.qb.DocType("Delivery Note")
	rows = (
		frappe.qb.from_(dn)
		.select(dn.name)
		.where((dn.docstatus == 1) & (dn.is_return == 1) & (dn.per_billed == 0) & (dn.status == "To Bill"))
	).run(pluck="name")

	if not rows:
		return

	(frappe.qb.update(dn).set(dn.status, "Return").where(dn.name.isin(rows))).run()
	frappe.logger("ram_custom").info(f"Delivery Note returns re-labelled 'Return': {len(rows)}")
