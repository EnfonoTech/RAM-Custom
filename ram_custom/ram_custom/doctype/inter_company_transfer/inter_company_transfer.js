function set_account_filters(frm) {
	frm.set_query("cost_of_branch_sales_account", () => ({
		filters: { company: frm.doc.from_company },
	}));
	frm.set_query("branch_sales_clearing_account", () => ({
		filters: { company: frm.doc.from_company },
	}));
	frm.set_query("from_company_receivable_account", () => ({
		filters: { company: frm.doc.from_company },
	}));
	frm.set_query("unrealized_branch_margin_account", () => ({
		filters: { company: frm.doc.from_company },
	}));
	frm.set_query("to_company_payable_account", () => ({
		filters: { company: frm.doc.to_company },
	}));
}

async function apply_account_heads_from_settings(frm) {
	if (!frm.doc.from_company || !frm.doc.to_company) return;
	const r = await frappe.call({
		method: "ram_custom.api.inter_company_transfer.get_transfer_account_heads",
		args: {
			from_company: frm.doc.from_company,
			to_company: frm.doc.to_company,
		},
	});
	const h = r.message || {};
	frm.set_value("cost_of_branch_sales_account", h.cost_of_branch_sales_account || "");
	frm.set_value("branch_sales_clearing_account", h.branch_sales_clearing_account || "");
	frm.set_value("from_company_receivable_account", h.from_company_receivable_account || "");
	frm.set_value("to_company_payable_account", h.to_company_payable_account || "");
	frm.set_value("unrealized_branch_margin_account", h.unrealized_branch_margin_account || "");
}

function recalculate_row_amounts(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) return;
	const stock_qty = flt(row.qty) * flt(row.conversion_factor || 1);
	const cost_rate = flt(row.cost_rate);
	const transfer_rate = flt(row.transfer_rate);
	const cost_value = stock_qty * cost_rate;
	const transfer_value = stock_qty * transfer_rate;
	const markup_value = transfer_value - cost_value;
	frappe.model.set_value(cdt, cdn, "cost_value", cost_value);
	frappe.model.set_value(cdt, cdn, "transfer_value", transfer_value);
	frappe.model.set_value(cdt, cdn, "markup_value", markup_value);
}

function recalculate_parent_totals(frm) {
	let total_cost = 0;
	let total_transfer = 0;
	(frm.doc.items || []).forEach((d) => {
		total_cost += flt(d.cost_value);
		total_transfer += flt(d.transfer_value);
	});
	frm.set_value("cost_value", total_cost);
	frm.set_value("transfer_value", total_transfer);
	frm.set_value("markup_value", flt(total_transfer - total_cost));
}

function fetch_conversion_factor(frm, cdt, cdn, item_code, uom) {
	if (!item_code || !uom) return;
	frappe.call({
		method: "erpnext.stock.get_item_details.get_conversion_factor",
		args: { item_code, uom },
		callback(r) {
			if (!r.exc && r.message) {
				frappe.model.set_value(
					cdt,
					cdn,
					"conversion_factor",
					flt(r.message.conversion_factor) || 1,
				);
				recalculate_row_amounts(cdt, cdn);
				recalculate_parent_totals(frm);
			}
		},
	});
}

async function on_item_row_item_code(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;
	const item = await frappe.db.get_value("Item", row.item_code, ["stock_uom"]);
	if (item && item.message) {
		const stock_uom = item.message.stock_uom || "";
		frappe.model.set_value(cdt, cdn, "stock_uom", stock_uom);
		frappe.model.set_value(cdt, cdn, "uom", stock_uom);
		if (stock_uom) {
			fetch_conversion_factor(frm, cdt, cdn, row.item_code, stock_uom);
		}
	}
	await set_row_cost_rate(frm, cdt, cdn);
}

async function set_row_cost_rate(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !row.source_warehouse) {
		recalculate_row_amounts(cdt, cdn);
		recalculate_parent_totals(frm);
		return;
	}
	const r = await frappe.call({
		method: "ram_custom.api.inter_company_transfer.get_item_valuation_rate",
		args: { item_code: row.item_code, warehouse: row.source_warehouse },
	});
	frappe.model.set_value(cdt, cdn, "cost_rate", flt(r.message || 0));
	recalculate_row_amounts(cdt, cdn);
	recalculate_parent_totals(frm);
}

frappe.ui.form.on("Inter Company Transfer", {
	setup(frm) {
		set_account_filters(frm);
		frm.set_query("default_source_warehouse", () => ({
			filters: { company: frm.doc.from_company },
		}));
		frm.set_query("default_target_warehouse", () => ({
			filters: { company: frm.doc.to_company },
		}));
		// When Stock Settings "allow_uom_with_conversion_rate_defined_in_item" is on,
		// get_item_uom_query returns only UOMs from Item's UOM Conversion Detail; otherwise all enabled UOMs.
		frm.set_query("uom", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			if (!row.item_code) {
				return { filters: [["name", "=", "__no_item_selected__"]] };
			}
			return {
				query: "erpnext.controllers.queries.get_item_uom_query",
				filters: { item_code: row.item_code },
			};
		});
	},
	refresh(frm) {
		set_account_filters(frm);
		(frm.doc.items || []).forEach((d) => {
			recalculate_row_amounts(d.doctype, d.name);
		});
		recalculate_parent_totals(frm);
	},
	async from_company(frm) {
		set_account_filters(frm);
		await apply_account_heads_from_settings(frm);
	},
	async to_company(frm) {
		set_account_filters(frm);
		await apply_account_heads_from_settings(frm);
	},
	async default_source_warehouse(frm) {
		for (const d of frm.doc.items || []) {
			if (!d.source_warehouse) {
				frappe.model.set_value(d.doctype, d.name, "source_warehouse", frm.doc.default_source_warehouse);
			}
			await set_row_cost_rate(frm, d.doctype, d.name);
		}
	},
	default_target_warehouse(frm) {
		(frm.doc.items || []).forEach((d) => {
			if (!d.target_warehouse) {
				frappe.model.set_value(d.doctype, d.name, "target_warehouse", frm.doc.default_target_warehouse);
			}
		});
	},
	items_remove(frm) {
		recalculate_parent_totals(frm);
	},
});

frappe.ui.form.on("Inter Company Transfer Item", {
	async item_code(frm, cdt, cdn) {
		await on_item_row_item_code(frm, cdt, cdn);
	},
	source_warehouse(frm, cdt, cdn) {
		set_row_cost_rate(frm, cdt, cdn);
	},
	qty(frm, cdt, cdn) {
		recalculate_row_amounts(cdt, cdn);
		recalculate_parent_totals(frm);
	},
	transfer_rate(frm, cdt, cdn) {
		recalculate_row_amounts(cdt, cdn);
		recalculate_parent_totals(frm);
	},
	uom(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.item_code && row.uom) {
			fetch_conversion_factor(frm, cdt, cdn, row.item_code, row.uom);
		}
	},
	conversion_factor(frm, cdt, cdn) {
		recalculate_row_amounts(cdt, cdn);
		recalculate_parent_totals(frm);
	},
	items_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (frm.doc.default_source_warehouse && !row.source_warehouse) {
			frappe.model.set_value(cdt, cdn, "source_warehouse", frm.doc.default_source_warehouse);
		}
		if (frm.doc.default_target_warehouse && !row.target_warehouse) {
			frappe.model.set_value(cdt, cdn, "target_warehouse", frm.doc.default_target_warehouse);
		}
		recalculate_row_amounts(cdt, cdn);
		recalculate_parent_totals(frm);
	},
});

frappe.ui.form.on("Inter Company Transfer Item", {
	form_render(frm) {
		frm.fields_dict.items.grid.get_field("source_warehouse").get_query = () => ({
			filters: { company: frm.doc.from_company },
		});
		frm.fields_dict.items.grid.get_field("target_warehouse").get_query = () => ({
			filters: { company: frm.doc.to_company },
		});
	},
});

