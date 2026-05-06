function set_account_filters(frm) {
	frm.set_query("branch_sales_clearing_account", () => ({
		filters: { company: frm.doc.from_company },
	}));
	frm.set_query("unrealized_branch_margin_account", () => ({
		filters: { company: frm.doc.from_company },
	}));
	frm.set_query("remote_company", () => ({
		filters: { disabled: 0 },
	}));
}

function clear_accounts(frm) {
	frm.set_value("branch_sales_clearing_account", "");
	frm.set_value("unrealized_branch_margin_account", "");
}

async function fetch_account_heads(frm) {
	if (!frm.doc.from_company) return;
	const is_remote = cint(frm.doc.is_remote_transfer) === 1;
	if (is_remote && !frm.doc.remote_company) return;
	if (!is_remote && !frm.doc.to_company) return;
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
	const is_remote = cint(frm.doc.is_remote_transfer) === 1;
	if (!frm.doc.from_company) {
		frappe.msgprint(__("Set From Company first"));
		return;
	}
	if (is_remote && !frm.doc.remote_company) {
		frappe.msgprint(__("Set Remote Company"));
		return;
	}
	if (!is_remote && !frm.doc.to_company) {
		frappe.msgprint(__("Set To Company"));
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
			remote_company: frm.doc.remote_company,
			is_remote_transfer: frm.doc.is_remote_transfer,
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

function toggle_remote_fields(frm) {
	const is_remote = cint(frm.doc.is_remote_transfer) === 1;
	frm.toggle_reqd("to_company", !is_remote);
	frm.toggle_reqd("remote_company", is_remote);
	frm.toggle_display("to_company", !is_remote);
	frm.toggle_display("remote_company", is_remote);
}

frappe.ui.form.on("Inter Company Cost Variance Reconciliation", {
	setup(frm) {
		set_account_filters(frm);
	},
	refresh(frm) {
		set_account_filters(frm);
		toggle_remote_fields(frm);
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
		clear_accounts(frm);
		fetch_account_heads(frm);
	},
	to_company(frm) {
		clear_accounts(frm);
		fetch_account_heads(frm);
	},
	remote_company(frm) {
		clear_accounts(frm);
		fetch_account_heads(frm);
	},
	is_remote_transfer(frm) {
		toggle_remote_fields(frm);
		clear_accounts(frm);
		if (cint(frm.doc.is_remote_transfer) === 1) {
			frm.set_value("to_company", "");
		} else {
			frm.set_value("remote_company", "");
		}
		fetch_account_heads(frm);
	},
});

frappe.ui.form.on("Inter Company Cost Variance Reconciliation Item", {
	items_remove(frm) {
		recompute_total_variance(frm);
	},
});
