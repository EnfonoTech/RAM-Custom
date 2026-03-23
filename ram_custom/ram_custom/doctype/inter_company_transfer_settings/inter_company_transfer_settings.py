# Copyright (c) 2026, ramees and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class InterCompanyTransferSettings(Document):
	def validate(self):
		pairs = []
		for d in self.company_accounts:
			if d.from_company and d.to_company:
				if d.from_company == d.to_company:
					frappe.throw(_("From Company and To Company cannot be same in settings row"))
				pairs.append((d.from_company, d.to_company))
		if len(pairs) != len(set(pairs)):
			frappe.throw(_("Duplicate From/To company pair is not allowed in settings"))

