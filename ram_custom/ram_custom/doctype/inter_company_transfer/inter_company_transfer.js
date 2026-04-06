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
	if (!frm.doc.from_company) return;
	if (cint(frm.doc.is_remote_transfer) === 1 && !frm.doc.remote_company) return;
	if (cint(frm.doc.is_remote_transfer) !== 1 && !frm.doc.to_company) return;
	const r = await frappe.call({
		method: "ram_custom.api.inter_company_transfer.get_transfer_account_heads",
		args: {
			from_company: frm.doc.from_company,
			to_company: frm.doc.to_company,
			remote_company: frm.doc.remote_company,
			is_remote_transfer: frm.doc.is_remote_transfer,
		},
	});
	const h = r.message || {};
	frm.set_value("cost_of_branch_sales_account", h.cost_of_branch_sales_account || "");
	frm.set_value("branch_sales_clearing_account", h.branch_sales_clearing_account || "");
	frm.set_value("from_company_receivable_account", h.from_company_receivable_account || "");
	frm.set_value("to_company_payable_account", h.to_company_payable_account || "");
	frm.set_value("unrealized_branch_margin_account", h.unrealized_branch_margin_account || "");
}

/** Child table updates via frappe.model.set_value always call frm.dirty() in Frappe. */
function ict_set_child_currency_silent(frm, cdt, cdn, fieldname, value) {
	const row = locals[cdt]?.[cdn];
	if (!row) return;
	const v = flt(value, 2);
	if (flt(row[fieldname], 2) === v) return;
	row[fieldname] = v;
	const pf = row.parentfield || "items";
	const grid = frm?.fields_dict?.[pf]?.grid;
	const gr = grid?.grid_rows_by_docname?.[cdn];
	if (gr) {
		gr.refresh_field(fieldname);
	}
}

function recalculate_row_amounts(frm, cdt, cdn, silent = false) {
	const row = locals[cdt][cdn];
	if (!row) return;
	const stock_qty = flt(row.qty) * flt(row.conversion_factor || 1);
	const cost_rate = flt(row.cost_rate);
	const transfer_rate = flt(row.transfer_rate);
	const cost_value = flt(stock_qty * cost_rate, 2);
	const transfer_value = flt(stock_qty * transfer_rate, 2);
	const markup_value = flt(transfer_value - cost_value, 2);
	if (silent && frm) {
		ict_set_child_currency_silent(frm, cdt, cdn, "cost_value", cost_value);
		ict_set_child_currency_silent(frm, cdt, cdn, "transfer_value", transfer_value);
		ict_set_child_currency_silent(frm, cdt, cdn, "markup_value", markup_value);
	} else {
		frappe.model.set_value(cdt, cdn, "cost_value", cost_value);
		frappe.model.set_value(cdt, cdn, "transfer_value", transfer_value);
		frappe.model.set_value(cdt, cdn, "markup_value", markup_value);
	}
}

function recalculate_parent_totals(frm, silent = false) {
	let total_cost = 0;
	let total_transfer = 0;
	(frm.doc.items || []).forEach((d) => {
		total_cost += flt(d.cost_value);
		total_transfer += flt(d.transfer_value);
	});
	total_cost = flt(total_cost, 2);
	total_transfer = flt(total_transfer, 2);
	const markup = flt(total_transfer - total_cost, 2);
	if (silent) {
		const tasks = [];
		if (flt(frm.doc.cost_value, 2) !== total_cost) {
			tasks.push(() => frm.set_value("cost_value", total_cost, false, true));
		}
		if (flt(frm.doc.transfer_value, 2) !== total_transfer) {
			tasks.push(() => frm.set_value("transfer_value", total_transfer, false, true));
		}
		if (flt(frm.doc.markup_value, 2) !== markup) {
			tasks.push(() => frm.set_value("markup_value", markup, false, true));
		}
		return tasks.length ? frappe.run_serially(tasks) : Promise.resolve();
	}
	return frappe.run_serially([
		() => frm.set_value("cost_value", total_cost),
		() => frm.set_value("transfer_value", total_transfer),
		() => frm.set_value("markup_value", markup),
	]);
}

function toggle_remote_mode_fields(frm) {
	const is_remote = cint(frm.doc.is_remote_transfer) === 1;
	frm.toggle_reqd("default_target_warehouse", !is_remote);
	frm.set_df_property("to_company_payable_account", "reqd", !is_remote);
	frm.toggle_reqd("to_company", !is_remote);
	frm.toggle_reqd("remote_company", is_remote);
	frm.toggle_display("to_company", !is_remote);
	frm.toggle_display("remote_company", is_remote);
	frm.fields_dict.items.grid.toggle_display("target_warehouse", !is_remote);
	if (is_remote) {
		if (frm.doc.to_company) {
			frm.set_value("to_company", "");
		}
		(frm.doc.items || []).forEach((d) => {
			if (d.target_warehouse) {
				frappe.model.set_value(d.doctype, d.name, "target_warehouse", "");
			}
		});
	}
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
				recalculate_row_amounts(frm, cdt, cdn, false);
				recalculate_parent_totals(frm, false);
				set_row_transfer_rate_from_price_list(frm, cdt, cdn);
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
	await set_row_transfer_rate_from_price_list(frm, cdt, cdn);
}

async function set_row_cost_rate(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !row.source_warehouse) {
		recalculate_row_amounts(frm, cdt, cdn, false);
		recalculate_parent_totals(frm, false);
		return;
	}
	const r = await frappe.call({
		method: "ram_custom.api.inter_company_transfer.get_item_valuation_rate",
		args: { item_code: row.item_code, warehouse: row.source_warehouse },
	});
	frappe.model.set_value(cdt, cdn, "cost_rate", flt(r.message || 0));
	recalculate_row_amounts(frm, cdt, cdn, false);
	recalculate_parent_totals(frm, false);
}

async function set_row_transfer_rate_from_price_list(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!frm.doc.transfer_price_list || !row?.item_code || !row.uom) {
		return;
	}
	const r = await frappe.call({
		method: "ram_custom.api.inter_company_transfer.get_inter_company_transfer_price_list_rate",
		args: {
			item_code: row.item_code,
			price_list: frm.doc.transfer_price_list,
			uom: row.uom,
			stock_uom: row.stock_uom,
			conversion_factor: row.conversion_factor,
			transaction_date: frm.doc.posting_date,
		},
	});
	const rate = flt(r.message || 0);
	if (rate > 0) {
		frappe.model.set_value(cdt, cdn, "transfer_rate", rate);
	}
	recalculate_row_amounts(frm, cdt, cdn, false);
	recalculate_parent_totals(frm, false);
}

async function refresh_transfer_rates_from_price_list_all_rows(frm) {
	if (!frm.doc.transfer_price_list) return;
	for (const d of frm.doc.items || []) {
		if (d.item_code && d.uom) {
			await set_row_transfer_rate_from_price_list(frm, d.doctype, d.name);
		}
	}
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
		frm.set_query("transfer_price_list", () => ({
			filters: { enabled: 1 },
		}));
		frm.set_query("remote_company", () => ({
			filters: { disabled: 0 },
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
		toggle_remote_mode_fields(frm);
		// Do not recalculate on every open: child set_value marks form dirty (Frappe limitation).
		if (cint(frm.doc.docstatus) !== 0) return;
		(frm.doc.items || []).forEach((d) => {
			recalculate_row_amounts(frm, d.doctype, d.name, true);
		});
		recalculate_parent_totals(frm, true);
	},
	async from_company(frm) {
		set_account_filters(frm);
		await apply_account_heads_from_settings(frm);
	},
	async to_company(frm) {
		set_account_filters(frm);
		await apply_account_heads_from_settings(frm);
	},
	is_remote_transfer(frm) {
		toggle_remote_mode_fields(frm);
		apply_account_heads_from_settings(frm);
	},
	remote_company(frm) {
		apply_account_heads_from_settings(frm);
	},
	async default_source_warehouse(frm) {
		for (const d of frm.doc.items || []) {
			frappe.model.set_value(d.doctype, d.name, "source_warehouse", frm.doc.default_source_warehouse);
			await set_row_cost_rate(frm, d.doctype, d.name);
			await set_row_transfer_rate_from_price_list(frm, d.doctype, d.name);
		}
	},
	async posting_date(frm) {
		await refresh_transfer_rates_from_price_list_all_rows(frm);
	},
	async transfer_price_list(frm) {
		await refresh_transfer_rates_from_price_list_all_rows(frm);
	},
	default_target_warehouse(frm) {
		if (cint(frm.doc.is_remote_transfer) === 1) return;
		(frm.doc.items || []).forEach((d) => {
			frappe.model.set_value(d.doctype, d.name, "target_warehouse", frm.doc.default_target_warehouse);
		});
	},
	items_remove(frm) {
		recalculate_parent_totals(frm, false);
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
		recalculate_row_amounts(frm, cdt, cdn, false);
		recalculate_parent_totals(frm, false);
	},
	transfer_rate(frm, cdt, cdn) {
		recalculate_row_amounts(frm, cdt, cdn, false);
		recalculate_parent_totals(frm, false);
	},
	uom(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.item_code && row.uom) {
			fetch_conversion_factor(frm, cdt, cdn, row.item_code, row.uom);
		}
	},
	async conversion_factor(frm, cdt, cdn) {
		recalculate_row_amounts(frm, cdt, cdn, false);
		recalculate_parent_totals(frm, false);
		await set_row_transfer_rate_from_price_list(frm, cdt, cdn);
	},
	async items_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (frm.doc.default_source_warehouse && !row.source_warehouse) {
			frappe.model.set_value(cdt, cdn, "source_warehouse", frm.doc.default_source_warehouse);
		}
		if (frm.doc.default_target_warehouse && !row.target_warehouse) {
			frappe.model.set_value(cdt, cdn, "target_warehouse", frm.doc.default_target_warehouse);
		}
		recalculate_row_amounts(frm, cdt, cdn, false);
		recalculate_parent_totals(frm, false);
		if (frm.doc.transfer_price_list) {
			await set_row_transfer_rate_from_price_list(frm, cdt, cdn);
		}
	},
	form_render(frm) {
		frm.fields_dict.items.grid.get_field("source_warehouse").get_query = () => ({
			filters: { company: frm.doc.from_company },
		});
		frm.fields_dict.items.grid.get_field("target_warehouse").get_query = () => ({
			filters: { company: frm.doc.to_company },
		});
	},
});

