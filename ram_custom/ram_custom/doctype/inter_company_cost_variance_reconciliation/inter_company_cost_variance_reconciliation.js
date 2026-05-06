function set_account_filters(frm) {
	frm.set_query("branch_sales_clearing_account", () => ({
		filters: { company: frm.doc.from_company },
	}));
	frm.set_query("unrealized_branch_margin_account", () => ({
		filters: { company: frm.doc.from_company },
	}));
}

async function fetch_account_heads(frm) {
	if (!frm.doc.from_company || !frm.doc.to_company) return;
	if (frm.doc.from_company === frm.doc.to_company) return;
	const r = await frappe.call({
		method: "ram_custom.api.inter_company_transfer.get_transfer_account_heads",
		args: {
			from_company: frm.doc.from_company,
			to_company: frm.doc.to_company,
			is_remote_transfer: 0,
		},
	});
	const h = r.message || {};
	if (h.branch_sales_clearing_account && !frm.doc.branch_sales_clearing_account) {
		frm.set_value("branch_sales_clearing_account", h.branch_sales_clearing_account);
	}
	if (h.unrealized_branch_margin_account && !frm.doc.unrealized_branch_margin_account) {
		frm.set_value("unrealized_branch_margin_account", h.unrealized_branch_margin_account);
	}
}

function recompute_total_variance(frm) {
	let total = 0;
	(frm.doc.items || []).forEach((d) => {
		total += flt(d.variance);
	});
	frm.set_value("total_variance", flt(total, 2));
}

async function fetch_variances(frm) {
	if (!frm.doc.from_company || !frm.doc.to_company) {
		frappe.msgprint(__("Set From Company and To Company first"));
		return;
	}
	if (!frm.doc.period_from || !frm.doc.period_to) {
		frappe.msgprint(__("Set Period From and Period To first"));
		return;
	}
	const r = await frappe.call({
		method:
			"ram_custom.ram_custom.doctype.inter_company_cost_variance_reconciliation."
			+ "inter_company_cost_variance_reconciliation.fetch_variance_rows",
		args: {
			from_company: frm.doc.from_company,
			to_company: frm.doc.to_company,
			period_from: frm.doc.period_from,
			period_to: frm.doc.period_to,
		},
	});
	const rows = r.message || [];
	frm.clear_table("items");
	if (!rows.length) {
		frappe.msgprint(__("No variances detected for the selected filters."));
		recompute_total_variance(frm);
		frm.refresh_field("items");
		return;
	}
	rows.forEach((row) => {
		const child = frm.add_child("items");
		Object.assign(child, row);
	});
	frm.refresh_field("items");
	recompute_total_variance(frm);
}

frappe.ui.form.on("Inter Company Cost Variance Reconciliation", {
	setup(frm) {
		set_account_filters(frm);
	},
	refresh(frm) {
		set_account_filters(frm);
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch Variances"), () => fetch_variances(frm));
		}
		if (frm.doc.docstatus === 1 && frm.doc.journal_entry) {
			frm.add_custom_button(__("View Journal Entry"), () => {
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
			});
		}
	},
	from_company(frm) {
		set_account_filters(frm);
		fetch_account_heads(frm);
	},
	to_company(frm) {
		fetch_account_heads(frm);
	},
});

frappe.ui.form.on("Inter Company Cost Variance Reconciliation Item", {
	items_remove(frm) {
		recompute_total_variance(frm);
	},
});
