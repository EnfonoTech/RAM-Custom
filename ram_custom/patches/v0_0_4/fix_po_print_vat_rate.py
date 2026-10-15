# Purchase Order prints hard-coded "15%" and amount * 0.15 on every line, so a
# zero-rated purchase (e.g. an import taxed with "VAT 0%") still printed 15% and a
# VAT amount per line while the document total correctly said 0.00.
#
# The two custom PO print formats now take the rate from the document's own
# "On Net Total" tax rows, so 15% stays 15% and a zero-rated order prints 0%.
# Only those two lines and one added variable are touched; idempotent, and
# `modified` is left alone.

import frappe

FORMATS = ("Purchase order new format", "Purchase Order Print Format")

RATE_SET = (
	'{% set vat = namespace(rate=0) %}'
	'{% for t in doc.taxes %}{% if t.charge_type == "On Net Total" %}'
	'{% set vat.rate = vat.rate + (t.rate or 0) %}{% endif %}{% endfor %}\n'
	"                                {% for item in doc.items %}"
)
OLD_LOOP = "                                {% for item in doc.items %}"
OLD_RATE = '<td class="text-center">15%</td>'
NEW_RATE = '<td class="text-center">{{ "%g"|format(vat.rate) }}%</td>'
OLD_AMOUNT = '"%.2f"|format((item.amount or 0) * 0.15)'
NEW_AMOUNT = '"%.2f"|format((item.amount or 0) * vat.rate / 100)'


def execute():
	for name in FORMATS:
		html = frappe.db.get_value("Print Format", name, "html")
		if not html or OLD_RATE not in html or OLD_AMOUNT not in html or "namespace(rate=0)" in html:
			continue
		if html.count(OLD_LOOP) != 1:
			frappe.log_error(f"{name}: unexpected item loop count, left unchanged", "PO print VAT patch")
			continue
		html = html.replace(OLD_LOOP, "                                " + RATE_SET.lstrip(), 1)
		html = html.replace(OLD_RATE, NEW_RATE).replace(OLD_AMOUNT, NEW_AMOUNT)
		frappe.db.set_value("Print Format", name, "html", html, update_modified=False)
