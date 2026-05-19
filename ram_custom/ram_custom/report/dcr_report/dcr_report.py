# Copyright (c) 2026, ramees and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": _("Type"),
            "fieldname": "type",
            "fieldtype": "Data",
            "width": 350
        },
        {
            "label": _("Total"),
            "fieldname": "total",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": _("Invoice"),
            "fieldname": "invoice_count",
            "fieldtype": "Int",
            "width": 120
        },
        {
            "label": _("Voucher Type"),
            "fieldname": "voucher_type",
            "fieldtype": "Data",
            "width": 0,
            "hidden": 1
        },
        {
            "label": _("Voucher No"),
            "fieldname": "voucher_no",
            "fieldtype": "Dynamic Link",
            "options": "voucher_type",
            "width": 0,
            "hidden": 1
        }
    ]


def get_data(filters):
    filters = filters or {}
    

    filters["company"] = filters.get("company") if filters.get("company") else None
    filters["cost_center"] = filters.get("cost_center") if filters.get("cost_center") else None

    date = filters.get("date")
    type_filter = filters.get("type")
    cost_center = filters.get("cost_center")
    company = filters.get("company")  

    types = [
        "Cash Sales",
        "Card/Bank Sales",
        "Credit Sales",
        "Cash Purchases",
        "Card/Bank Purchases",
        "Credit Purchases",
        "Sales Return",
        "Purchase Return",
        "Customer Receipts",
        "Supplier Payments",
        "Bank Receipts",
        "Bank Payments",
        "Cash Receipts",
        "Cash Payments",
        "Journal Entry",
        "Internal Transfer",
    ]

    # If type filter is selected, show only that type  
    if type_filter:
        types = [type_filter]

    result = []

    for t in types:
        total = 0
        count = 0
        paid_rows = []

        # Voucher type conditions
        if t in ["Cash Sales", "Card/Bank Sales", "Credit Sales"]:
            paid_rows = fetch_sales_invoices(t, date, company,cost_center)

        elif t in ["Cash Purchases", "Card/Bank Purchases", "Credit Purchases"]:
            paid_rows = fetch_purchase_invoices(t, date, company,cost_center)

        elif t == "Sales Return":
            paid_rows = get_sales_returns(date,company, cost_center)
        elif t == "Purchase Return":
            paid_rows = get_purchase_returns(date,company, cost_center)

        elif t == "Customer Receipts":
            paid_rows = get_customer_receipts(date, company,cost_center)
        elif t == "Supplier Payments":
            paid_rows = get_supplier_payments(date, company,cost_center)
        elif t == "Internal Transfer":
            paid_rows = get_internal_transfers(date, company, cost_center)


        elif t in ["Bank Receipts", "Bank Payments", "Cash Receipts", "Cash Payments", "Journal Entry"]:
            paid_rows = get_journal_entries(date, t, company,cost_center)


        total = sum(r.get("amount", 0) or 0 for r in paid_rows)
        count = len(paid_rows)

        # Add total row
        result.append({
            "type": t,
            "total": total,
            "invoice_count": count,
            "indent": 0
        })

        # Add individual invoice/payment rows
        for row in paid_rows:
            result.append({
                "type": f"{row.get('voucher_type', row.get('document',''))} {row.get('voucher_no', row.get('id',''))}",
                "total": row.get("amount", 0),
                "invoice_count": "",
                "voucher_type": row.get("voucher_type", row.get("document","")),
                "voucher_no": row.get("voucher_no", row.get("id","")),
                "indent": 1
            })

    return result


def fetch_sales_invoices(t, date,company, cost_center):

    if t == "Cash Sales":

        amount_field = """
            IFNULL(
                CASE 
                    WHEN si.is_pos = 1 THEN SUM(sip.amount)
                    ELSE SUM(per.allocated_amount)
                END
            ,0)
        """

        date_condition = """
            AND si.posting_date = %(date)s
            AND (
                (
                    si.is_pos = 0
                    AND pe.posting_date <= si.posting_date
                    AND pe.mode_of_payment IN (
                        SELECT name FROM `tabMode of Payment`
                        WHERE type = 'Cash'
                    )
                )
                OR
                (
                    si.is_pos = 1
                    AND sip.mode_of_payment IN (
                        SELECT name FROM `tabMode of Payment`
                        WHERE type = 'Cash'
                    )
                )
            )
        """

        join_type = "LEFT"

    elif t == "Card/Bank Sales":

        amount_field = """
            IFNULL(
                CASE 
                    WHEN si.is_pos = 1 THEN SUM(sip.amount)
                    ELSE SUM(per.allocated_amount)
                END
            ,0)
        """

        date_condition = """
            AND si.posting_date = %(date)s
            AND (
                (
                    si.is_pos = 0
                    AND pe.posting_date = %(date)s
                    AND pe.mode_of_payment IN (
                        SELECT name FROM `tabMode of Payment`
                        WHERE type IN ('Bank','Card')
                    )
                )
                OR
                (
                    si.is_pos = 1
                    AND sip.mode_of_payment IN (
                        SELECT name FROM `tabMode of Payment`
                        WHERE type IN ('Bank','Card')
                    )
                )
            )
        """

        join_type = "LEFT"

    else:  # Credit Sales
        amount_field = "si.grand_total"
        date_condition = """
            AND si.posting_date = %(date)s
            AND si.is_pos = 0
            AND NOT EXISTS (
                SELECT 1
                FROM `tabPayment Entry Reference` per2
                INNER JOIN `tabPayment Entry` pe2
                    ON pe2.name = per2.parent
                WHERE per2.reference_name = si.name
                    AND per2.reference_doctype = 'Sales Invoice'
                    AND pe2.docstatus = 1
                    AND pe2.posting_date = si.posting_date
            )
        """

        join_type = "LEFT"


    query = f"""
        SELECT si.name AS voucher_no,
               {amount_field} AS amount,
               'Sales Invoice' AS voucher_type
        FROM `tabSales Invoice` si
        {join_type} JOIN `tabPayment Entry Reference` per
            ON per.reference_name = si.name
            AND per.reference_doctype='Sales Invoice'
        {join_type} JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
            
            
         LEFT JOIN `tabSales Invoice Payment` sip
            ON sip.parent = si.name
        WHERE si.docstatus IN (0,1)
              AND si.is_return=0
              {date_condition}
              AND ( %(company)s IS NULL OR %(company)s = '' OR si.company = %(company)s )
              AND ( %(cost_center)s IS NULL OR %(cost_center)s = '' OR si.cost_center = %(cost_center)s )
        GROUP BY si.name
    """

    return frappe.db.sql(query, {"date": date, "company": company, "cost_center": cost_center}, as_dict=True)


def fetch_purchase_invoices(t, date,company, cost_center):
    """Fetch Purchase Invoice rows per type & MoP"""

    date_condition = f"AND pi.posting_date = '{date}'" if date else ""

    if t == "Cash Purchases":
        amount_field = "IFNULL(SUM(per.allocated_amount),0)"
        date_condition = """
            AND pi.posting_date = %(date)s
            AND pe.posting_date = %(date)s
            AND pe.mode_of_payment IN (
                SELECT name FROM `tabMode of Payment` WHERE type='Cash'
            )
        """

    elif t == "Card/Bank Purchases":
        amount_field = "IFNULL(SUM(per.allocated_amount),0)"
        date_condition = """
            AND pi.posting_date = %(date)s
            AND pe.posting_date = %(date)s
            AND pe.mode_of_payment IN (
                SELECT name FROM `tabMode of Payment` WHERE type IN ('Bank','Card')
            )
        """

    else:  # Credit Purchases
        amount_field = "pi.grand_total"
        date_condition = """
            AND pi.posting_date = %(date)s
            AND NOT EXISTS (
                SELECT 1
                FROM `tabPayment Entry Reference` per2
                INNER JOIN `tabPayment Entry` pe2
                    ON pe2.name = per2.parent
                WHERE per2.reference_name = pi.name
                    AND per2.reference_doctype = 'Purchase Invoice'
                    AND pe2.docstatus = 1
                    AND pe2.posting_date = %(date)s
            )
        """

    query = f"""
        SELECT pi.name AS voucher_no,
               {amount_field} AS amount,
               'Purchase Invoice' AS voucher_type
        FROM `tabPurchase Invoice` pi
        LEFT JOIN `tabPayment Entry Reference` per
            ON per.reference_name = pi.name AND per.reference_doctype='Purchase Invoice'
        LEFT JOIN `tabPayment Entry` pe
            ON pe.name = per.parent 
        WHERE pi.docstatus IN (0,1)
              AND pi.is_return=0
              {date_condition}
              AND ( %(company)s IS NULL OR %(company)s = '' OR pi.company = %(company)s )
              AND ( %(cost_center)s IS NULL OR %(cost_center)s = '' OR pi.cost_center = %(cost_center)s )
        GROUP BY pi.name
    """

    return frappe.db.sql(query, {"date": date, "company": company,"cost_center": cost_center}, as_dict=True)


def get_sales_returns(date,company,cost_center):
    # Fetch sales returns for the exact filter date only
    data = frappe.db.sql("""
        SELECT
            'Sales Invoice' AS voucher_type,
            si.name AS voucher_no,
            CASE
                WHEN si.grand_total - COALESCE(SUM(
                    CASE WHEN pe.posting_date = %(date)s AND pe.docstatus=1 
                        THEN per.allocated_amount ELSE 0 END
                ),0) = 0 THEN 'Paid'
                WHEN COALESCE(SUM(
                    CASE WHEN pe.posting_date = %(date)s AND pe.docstatus=1 
                        THEN per.allocated_amount ELSE 0 END
                ),0) = 0 THEN 'Unpaid'
                ELSE 'Partially Paid'
            END AS status,
            si.grand_total AS invoice_total,
            CASE
                WHEN COALESCE(SUM(
                    CASE WHEN pe.posting_date = %(date)s AND pe.docstatus=1 
                        THEN per.allocated_amount ELSE 0 END
                ),0) > 0
                THEN COALESCE(SUM(
                    CASE WHEN pe.posting_date = %(date)s AND pe.docstatus=1 
                        THEN per.allocated_amount ELSE 0 END
                ),0)
                ELSE si.grand_total
            END AS amount,
            COUNT(si.name) OVER () AS total_count
        FROM `tabSales Invoice` si
        LEFT JOIN `tabPayment Entry Reference` per
            ON per.reference_name=si.name AND per.reference_doctype='Sales Invoice'
        LEFT JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
        WHERE si.docstatus IN (0,1)
            AND si.is_return=1
            AND si.posting_date = %(date)s
            AND ( %(company)s IS NULL OR %(company)s = '' OR si.company = %(company)s )
            AND ( %(cost_center)s IS NULL OR %(cost_center)s = '' OR si.cost_center = %(cost_center)s )
        GROUP BY si.name, si.grand_total
        ORDER BY si.posting_date ASC
    """, {"date": date, "company": company,"cost_center": cost_center}, as_dict=True)

    return data


def get_purchase_returns(date,company,cost_center):
    # Fetch purchase returns for the exact invoice posting date only 
    return frappe.db.sql("""
        SELECT
            'Purchase Return' AS document,
            pi.name AS id,
            CASE
                WHEN pi.outstanding_amount = 0 THEN 'Paid'
                WHEN pi.outstanding_amount = pi.grand_total THEN 'Unpaid'
                ELSE 'Partially Paid'
            END AS status,
            pi.grand_total AS invoice_total,
            IFNULL(SUM(
                CASE WHEN pe.docstatus=1 THEN per.allocated_amount ELSE 0 END
            ),0) AS amount
        FROM `tabPurchase Invoice` pi
        LEFT JOIN `tabPayment Entry Reference` per
            ON per.reference_name=pi.name AND per.reference_doctype='Purchase Invoice'
        LEFT JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
        WHERE pi.docstatus IN (0,1) AND pi.is_return=1
              AND pi.posting_date = %(date)s
              AND ( %(company)s IS NULL OR %(company)s = '' OR pi.company = %(company)s )
              AND ( %(cost_center)s IS NULL OR %(cost_center)s = '' OR pi.cost_center = %(cost_center)s )
        GROUP BY pi.name
        ORDER BY pi.posting_date ASC
    """, {"date": date,"company": company, "cost_center": cost_center}, as_dict=True)


def get_customer_receipts(date, company=None, cost_center=None):
    return frappe.db.sql("""
        SELECT
            'Payment Entry' AS document,
            pe.name AS id,
            'Paid' AS status,
            pe.paid_amount AS invoice_total,
            pe.paid_amount AS amount
        FROM `tabPayment Entry` pe
        INNER JOIN `tabPayment Entry Reference` per
            ON per.parent = pe.name
            AND per.reference_doctype = 'Sales Invoice'
        INNER JOIN `tabSales Invoice` si
            ON si.name = per.reference_name
        WHERE pe.docstatus IN (0,1)
              AND pe.posting_date = %(date)s
              AND pe.party_type = 'Customer'
               AND pe.posting_date != si.posting_date
              AND ( %(company)s IS NULL OR %(company)s = '' OR pe.company = %(company)s )
              AND ( %(cost_center)s IS NULL OR %(cost_center)s = '' OR pe.cost_center = %(cost_center)s )
    """, {
        "date": date,
        "company": company,
        "cost_center": cost_center
    }, as_dict=True)


def get_supplier_payments(date, company, cost_center):
    return frappe.db.sql("""
        SELECT
            'Payment Entry' AS document,
            pe.name AS id,
            'Paid' AS status,
            pe.paid_amount AS invoice_total,
            pe.paid_amount AS amount
        FROM `tabPayment Entry` pe
        LEFT JOIN `tabPayment Entry Reference` per
            ON per.parent = pe.name
            AND per.reference_doctype = 'Purchase Invoice'
        LEFT JOIN `tabPurchase Invoice` pi
            ON pi.name = per.reference_name
        WHERE pe.docstatus IN (0,1)
              AND pe.posting_date = %(date)s
              AND pe.party_type = 'Supplier'
              AND ( %(company)s IS NULL OR %(company)s = '' OR pe.company = %(company)s )
              AND (
                    per.name IS NULL 
                    OR pi.posting_date < pe.posting_date
                  )
              AND ( %(cost_center)s IS NULL OR %(cost_center)s = '' OR pe.cost_center = %(cost_center)s )
        GROUP BY pe.name, pe.paid_amount
        ORDER BY pe.posting_date ASC
    """, {
        "date": date,
        "company": company,
        "cost_center": cost_center
    }, as_dict=True)

def get_journal_entries(date, report_type=None, company=None, cost_center=None):
    if report_type in ("Bank Receipts", "Bank Payments", "Cash Receipts", "Cash Payments"):
        if report_type == "Bank Receipts":
            conditions = "acc.account_type='Bank' AND jea.debit>0"
        elif report_type == "Bank Payments":
            conditions = "acc.account_type='Bank' AND jea.credit>0"
        elif report_type == "Cash Receipts":
            conditions = "acc.account_type='Cash' AND jea.debit>0"
        elif report_type == "Cash Payments":
            conditions = "acc.account_type='Cash' AND jea.credit>0"

        return frappe.db.sql(f"""
            SELECT
                'Journal Entry' AS document,
                je.name AS id,
                'Posted' AS status,
                (jea.debit + jea.credit) AS invoice_total,
                CASE WHEN jea.debit>0 THEN jea.debit ELSE jea.credit END AS amount
            FROM `tabJournal Entry` je
            INNER JOIN `tabJournal Entry Account` jea
                ON jea.parent=je.name
            INNER JOIN `tabAccount` acc
                ON acc.name=jea.account
            WHERE je.docstatus IN (0,1)
                  AND je.posting_date=%(date)s
                  AND {conditions}
                  AND (%(company)s IS NULL OR je.company = %(company)s)
                  AND (%(cost_center)s IS NULL OR jea.cost_center = %(cost_center)s)
        """, {"date": date,"company": company,"cost_center": cost_center}, as_dict=True)

    else:
        # Other Journal Entries → Only non-Bank/non-Cash entries entirely
        return frappe.db.sql("""
            SELECT
                'Journal Entry' AS document,
                je.name AS id,
                'Posted' AS status,
                SUM(jea.debit + jea.credit) AS invoice_total,
                SUM(CASE WHEN jea.debit>0 THEN jea.debit ELSE jea.credit END) AS amount
            FROM `tabJournal Entry` je
            INNER JOIN `tabJournal Entry Account` jea
                ON jea.parent = je.name
            INNER JOIN `tabAccount` acc
                ON acc.name = jea.account
            WHERE je.docstatus IN (0,1)
                  AND je.posting_date = %(date)s
                  AND (%(company)s IS NULL OR je.company = %(company)s)
                  AND (%(cost_center)s IS NULL OR jea.cost_center = %(cost_center)s)
            GROUP BY je.name
            HAVING SUM(CASE WHEN acc.account_type IN ('Bank','Cash') THEN 1 ELSE 0 END) = 0
        """, {"date": date, "company": company,"cost_center": cost_center}, as_dict=True)


def get_internal_transfers(date, company=None, cost_center=None):

    return frappe.db.sql("""
        SELECT
            'Payment Entry' AS voucher_type,
            pe.name AS voucher_no,
            'Internal Transfer' AS status,
            pe.paid_amount AS amount,
            pe.paid_amount AS invoice_total
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus IN (0,1)
              AND pe.payment_type = 'Internal Transfer'
              AND pe.posting_date = %(date)s
              AND ( %(company)s IS NULL OR pe.company = %(company)s )
              AND ( %(cost_center)s IS NULL OR pe.cost_center = %(cost_center)s )
    """, {
        "date": date,
        "company": company,
        "cost_center": cost_center
    }, as_dict=True)