async function computeCostRateForRow(frm, cdt, cdn) {
	if (cint(frm.doc.docstatus) === 1) return;
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
			// Helps debugging when the server can't resolve Bin valuation.
			// eslint-disable-next-line no-console
			console.error("Cost Rate fetch failed", err);
		},
	});

	const rate = flt(r.message || 0);
	// Use cdt/cdn to reliably update grid row fields.
	frappe.model.set_value(cdt, cdn, "cost_rate", rate);
}

function shouldComputeCostRate(row) {
	if (!row || !row.item_code) return false;
	// Avoid excessive calls while form reloads:
	// compute when missing OR when already-computed value is 0.
	// (0 can be a real valuation rate; recompute is acceptable and makes it robust.)
	if (row.cost_rate === undefined || row.cost_rate === null) return true;
	return flt(row.cost_rate) <= 0;
}

async function computeCostRatesForParent(frm, force = false) {
	if (cint(frm.doc.docstatus) === 1) return;
	for (const row of frm.doc.items || []) {
		// row.name is the cdn for child tables.
		const cdt = row.doctype;
		const cdn = row.name;
		const current = locals?.[cdt]?.[cdn] || row;
		if (!force && !shouldComputeCostRate(current)) continue;
		await computeCostRateForRow(frm, cdt, cdn);
	}
}

frappe.ui.form.on("Sales Invoice Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		// Warehouse is often auto-filled right after item selection;
		// recompute shortly after to catch that.
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Delivery Note Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Quotation Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Sales Order Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Purchase Receipt Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Purchase Order Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Purchase Invoice Item", {
	item_code(frm, cdt, cdn) {
		if (!locals?.[cdt]?.[cdn]?.item_code) return;
		setTimeout(() => computeCostRateForRow(frm, cdt, cdn), 250);
	},
	warehouse(frm, cdt, cdn) {
		computeCostRateForRow(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		// SI can be created from SO/DN with copied cost_rate; force current valuation fetch.
		computeCostRatesForParent(frm, true);
	},
});

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		computeCostRatesForParent(frm);
	},
});

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		computeCostRatesForParent(frm);
	},
});

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		computeCostRatesForParent(frm);
	},
});

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		computeCostRatesForParent(frm);
	},
});

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		computeCostRatesForParent(frm);
	},
});

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		computeCostRatesForParent(frm);
	},
});
