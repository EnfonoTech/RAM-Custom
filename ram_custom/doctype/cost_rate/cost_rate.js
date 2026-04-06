/** Update child row without marking form dirty (Frappe child model.on always calls frm.dirty()). */
function ram_custom_set_child_currencyQuiet(frm, cdt, cdn, fieldname, value) {
	const row = locals?.[cdt]?.[cdn];
	if (!row) return;
	const v = flt(value);
	if (flt(row[fieldname]) === v) return;
	row[fieldname] = v;
	const pf = row.parentfield || "items";
	const grid = frm.fields_dict?.[pf]?.grid;
	const gr = grid?.grid_rows_by_docname?.[cdn];
	if (gr) {
		gr.refresh_field(fieldname);
	}
}

async function computeCostRateForRow(frm, cdt, cdn, silent = false) {
	if (frm.doc.docstatus !== 0) return;
	const row = locals?.[cdt]?.[cdn];
	if (!row || !row.item_code) return;
	const company = frm.doc.company;
	const warehouse = row.warehouse || row.from_warehouse || row.target_warehouse || null;
	if (!company) return;

	const r = await frappe.call({
		method: "ram_custom.api.cost_rate.get_cost_rate",
		args: {
			item_code: row.item_code,
			company,
			warehouse,
		},
		error: (err) => {
			// eslint-disable-next-line no-console
			console.error("Cost Rate fetch failed", err);
		},
	});

	const rate = flt(r.message || 0);
	if (silent) {
		ram_custom_set_child_currencyQuiet(frm, cdt, cdn, "cost_rate", rate);
	} else {
		frappe.model.set_value(cdt, cdn, "cost_rate", rate);
	}
}

function shouldComputeCostRate(row) {
	if (!row || !row.item_code) return false;
	if (row.cost_rate === undefined || row.cost_rate === null) return true;
	return flt(row.cost_rate) <= 0;
}

async function computeCostRatesForParent(frm, force = false, silent = true) {
	if (frm.doc.docstatus !== 0) return;
	for (const row of frm.doc.items || []) {
		const cdt = row.doctype;
		const cdn = row.name;
		const current = locals?.[cdt]?.[cdn] || row;
		if (!force && !shouldComputeCostRate(current)) continue;
		await computeCostRateForRow(frm, cdt, cdn, silent);
	}
}

frappe.ui.form.on("Sales Invoice Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn, false), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn, false);
	},
});

frappe.ui.form.on("Delivery Note Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn, false), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn, false);
	},
});

frappe.ui.form.on("Quotation Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn, false), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn, false);
	},
});

frappe.ui.form.on("Sales Order Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn, false), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn, false);
	},
});

frappe.ui.form.on("Purchase Receipt Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn, false), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn, false);
	},
});

frappe.ui.form.on("Purchase Order Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn, false), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn, false);
	},
});

frappe.ui.form.on("Purchase Invoice Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn, false), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn, false);
	},
});

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		computeCostRatesForParent(frm, true, true);
	},
});

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		computeCostRatesForParent(frm, false, true);
	},
});

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		computeCostRatesForParent(frm, false, true);
	},
});

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		computeCostRatesForParent(frm, false, true);
	},
});

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		computeCostRatesForParent(frm, false, true);
	},
});

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		computeCostRatesForParent(frm, false, true);
	},
});

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		computeCostRatesForParent(frm, false, true);
	},
});
