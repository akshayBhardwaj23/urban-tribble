#!/usr/bin/env python3
"""Generate Slick Styles demo Excel files for Snaptix upload templates."""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
random.seed(42)

# --- Catalog (meaningful for a phone-case DTC + marketplace brand) ---

PHONE_MODELS = [
    "iPhone 15 Pro Max",
    "iPhone 15 Pro",
    "iPhone 14",
    "Samsung Galaxy S24 Ultra",
    "Samsung Galaxy S24",
    "Google Pixel 8 Pro",
    "OnePlus 12",
    "Nothing Phone (2)",
]

CASE_LINES = [
    ("Clear Grip", "Clear/Slim", 18, 6.20, 0.62),
    ("MagSafe Slim", "MagSafe", 32, 8.50, 0.58),
    ("Rugged Armor", "Rugged", 28, 11.00, 0.52),
    ("Leather Wallet", "Wallet", 45, 14.50, 0.48),
    ("Eco Cork", "Sustainable", 24, 9.80, 0.55),
    ("Glitter Glam", "Fashion", 22, 7.40, 0.60),
]

CHANNELS = ["Website DTC", "Amazon India", "Flipkart", "B2B Wholesale", "Retail Partners"]
REGIONS = ["North", "South", "East", "West", "Metro"]
SALES_REPS = ["Ananya Iyer", "Rohan Kapoor", "Meera Nair", "Karan Desai", "Priya Menon"]
AD_CHANNELS = ["Google Ads", "Meta Ads", "Instagram", "YouTube", "Influencer", "Email"]
VENDORS = [
    "Shenzhen CaseWorks Co.",
    "Mumbai Packaging Hub",
    "Delhi Print & Label",
    "Bangalore 3PL Express",
    "Global MagSafe Components",
]
EXPENSE_CATEGORIES = [
    "Product COGS",
    "Marketplace Fees",
    "Fulfillment & Shipping",
    "Paid Advertising",
    "Influencer Fees",
    "Warehouse Rent",
    "Customer Support",
    "Returns Processing",
]


def _month_starts(year: int = 2024, months: int = 14) -> list[date]:
    start = date(year, 1, 1)
    out = []
    d = start
    for _ in range(months):
        out.append(d)
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)
    return out


def _write(df: pd.DataFrame, rel_path: str) -> None:
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, sheet_name="Data")
    print(f"  wrote {path.relative_to(ROOT)}")


def generate_monthly_business_review() -> None:
    months = _month_starts(2024, 14)

    # Revenue / expenses / profit by channel & month (MBR core)
    rows = []
    for m in months:
        for ch in CHANNELS:
            base_units = {
                "Website DTC": 4200,
                "Amazon India": 6800,
                "Flipkart": 3100,
                "B2B Wholesale": 1900,
                "Retail Partners": 850,
            }[ch]
            season = 1.15 if m.month in (10, 11, 12) else (0.92 if m.month in (6, 7) else 1.0)
            growth = 1 + (m.month - 1) * 0.012
            units = int(base_units * season * growth * random.uniform(0.92, 1.08))
            asp = random.uniform(22, 38) if ch != "B2B Wholesale" else random.uniform(14, 22)
            revenue = round(units * asp, 2)
            fee_rate = {"Website DTC": 0.08, "Amazon India": 0.18, "Flipkart": 0.15, "B2B Wholesale": 0.04, "Retail Partners": 0.10}[ch]
            cogs_rate = 0.38
            expenses = round(revenue * (cogs_rate + fee_rate) + random.uniform(8000, 25000), 2)
            profit = round(revenue - expenses, 2)
            rows.append(
                {
                    "month": m.replace(day=1).isoformat(),
                    "sales_channel": ch,
                    "region": random.choice(REGIONS),
                    "units_sold": units,
                    "gross_revenue_inr": revenue,
                    "operating_expenses_inr": expenses,
                    "operating_profit_inr": profit,
                }
            )
    _write(pd.DataFrame(rows), "01-monthly-business-review/monthly_revenue_and_profit_by_channel.xlsx")

    # Orders summary for leadership
    order_rows = []
    oid = 10000
    for m in months[-6:]:
        for _ in range(random.randint(180, 260)):
            line = random.choice(CASE_LINES)
            model = random.choice(PHONE_MODELS)
            qty = random.choices([1, 2, 3], weights=[70, 22, 8])[0]
            price = round(line[2] * random.uniform(0.95, 1.12), 2)
            order_rows.append(
                {
                    "order_date": (m + timedelta(days=random.randint(0, 27))).isoformat(),
                    "order_id": f"SS-{oid}",
                    "phone_model": model,
                    "case_name": line[0],
                    "case_category": line[1],
                    "quantity": qty,
                    "unit_price_inr": price,
                    "order_total_inr": round(price * qty, 2),
                    "sales_channel": random.choice(CHANNELS),
                    "fulfillment_status": random.choices(
                        ["Delivered", "Shipped", "Returned"], weights=[88, 8, 4]
                    )[0],
                }
            )
            oid += 1
    _write(pd.DataFrame(order_rows), "01-monthly-business-review/recent_orders_detail.xlsx")

    # KPI scorecard style
    kpi_rows = []
    for m in months:
        kpi_rows.append(
            {
                "month": m.replace(day=1).isoformat(),
                "website_sessions": int(random.uniform(85000, 140000) * (1.2 if m.month in (10, 11) else 1)),
                "conversion_rate_pct": round(random.uniform(2.1, 3.8), 2),
                "average_order_value_inr": round(random.uniform(26, 42), 2),
                "return_rate_pct": round(random.uniform(3.5, 7.2), 2),
                "repeat_customer_rate_pct": round(random.uniform(18, 32), 2),
                "inventory_days_on_hand": int(random.uniform(38, 72)),
            }
        )
    _write(pd.DataFrame(kpi_rows), "01-monthly-business-review/monthly_kpi_scorecard.xlsx")


def generate_profit_leak_audit() -> None:
    # Product margin — show leather & glitter with promo pressure
    margin_rows = []
    for line in CASE_LINES:
        for model in random.sample(PHONE_MODELS, k=5):
            units = random.randint(400, 3200)
            retail = line[2]
            cogs = line[3]
            discount_pct = round(
                random.uniform(0, 22)
                if line[0] in ("Glitter Glam", "Leather Wallet")
                else random.uniform(0, 12),
                1,
            )
            net_price = retail * (1 - discount_pct / 100)
            revenue = round(units * net_price, 2)
            total_cogs = round(units * cogs, 2)
            margin = round(revenue - total_cogs, 2)
            margin_rows.append(
                {
                    "sku": f"SS-{line[0][:3].upper()}-{model.split()[-1][:3].upper()}",
                    "case_name": line[0],
                    "phone_model": model,
                    "units_sold_qtd": units,
                    "list_price_inr": retail,
                    "avg_discount_pct": discount_pct,
                    "net_revenue_inr": revenue,
                    "cogs_inr": total_cogs,
                    "gross_margin_inr": margin,
                    "gross_margin_pct": round(100 * margin / revenue, 1) if revenue else 0,
                }
            )
    _write(pd.DataFrame(margin_rows), "02-profit-leak-audit/product_margin_and_cogs_by_sku.xlsx")

    vendor_rows = []
    for v in VENDORS:
        for month in _month_starts(2024, 12):
            spend = round(
                random.uniform(120000, 890000)
                * (1.4 if "CaseWorks" in v else 1.0),
                2,
            )
            vendor_rows.append(
                {
                    "invoice_month": month.replace(day=1).isoformat(),
                    "vendor_name": v,
                    "expense_category": random.choice(
                        ["Product COGS", "Fulfillment & Shipping", "Packaging Materials"]
                    ),
                    "amount_inr": spend,
                    "payment_status": random.choices(["Paid", "Pending"], weights=[85, 15])[0],
                    "notes": random.choice(
                        [
                            "Bulk case shells — Qty aligned to forecast",
                            "Last-mile packaging consumables",
                            "MagSafe ring batch — iPhone 15 series",
                            "",
                        ]
                    ),
                }
            )
    _write(pd.DataFrame(vendor_rows), "02-profit-leak-audit/vendor_and_fulfillment_spend.xlsx")

    leak_rows = []
    for month in _month_starts(2024, 12):
        for ch in CHANNELS:
            returns = int(random.uniform(80, 420) * (1.3 if ch == "Amazon India" else 1))
            promo = round(random.uniform(15000, 95000), 2)
            chargebacks = round(random.uniform(2000, 12000) if ch in ("Amazon India", "Flipkart") else 500, 2)
            leak_rows.append(
                {
                    "month": month.replace(day=1).isoformat(),
                    "channel": ch,
                    "promo_discount_inr": promo,
                    "return_units": returns,
                    "return_cost_inr": round(returns * random.uniform(8, 14), 2),
                    "marketplace_chargebacks_inr": chargebacks,
                    "defective_replacements_inr": round(random.uniform(3000, 18000), 2),
                }
            )
    _write(pd.DataFrame(leak_rows), "02-profit-leak-audit/discounts_returns_and_chargebacks.xlsx")


def generate_sales_performance() -> None:
    rows = []
    for rep in SALES_REPS:
        for region in REGIONS:
            for month in _month_starts(2024, 12):
                quota = round(random.uniform(450000, 920000), 2)
                attainment = round(quota * random.uniform(0.72, 1.18), 2)
                rows.append(
                    {
                        "month": month.replace(day=1).isoformat(),
                        "sales_rep": rep,
                        "region": region,
                        "quota_inr": quota,
                        "booked_revenue_inr": attainment,
                        "attainment_pct": round(100 * attainment / quota, 1),
                        "new_accounts": random.randint(2, 14),
                        "cases_sold_units": int(attainment / random.uniform(18, 28)),
                    }
                )
    _write(pd.DataFrame(rows), "03-sales-performance/wholesale_sales_by_rep_and_region.xlsx")

    product_rows = []
    for month in _month_starts(2024, 10):
        for model in PHONE_MODELS:
            for line in CASE_LINES:
                if random.random() > 0.55:
                    continue
                units = random.randint(50, 1800)
                product_rows.append(
                    {
                        "month": month.replace(day=1).isoformat(),
                        "phone_model": model,
                        "case_name": line[0],
                        "case_category": line[1],
                        "units_sold": units,
                        "revenue_inr": round(units * line[2] * random.uniform(0.9, 1.05), 2),
                        "primary_channel": random.choice(CHANNELS),
                        "top_city": random.choice(
                            ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Pune", "Chennai"]
                        ),
                    }
                )
    _write(pd.DataFrame(product_rows), "03-sales-performance/revenue_by_phone_model_and_case.xlsx")

    pipeline = []
    for rep in SALES_REPS:
        for i in range(random.randint(6, 12)):
            stage = random.choice(
                ["Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
            )
            amount = round(random.uniform(80000, 650000), 2)
            pipeline.append(
                {
                    "opportunity_id": f"OPP-{rep.split()[0][:2].upper()}{random.randint(1000,9999)}",
                    "account_name": random.choice(
                        [
                            "Mobile Mart Delhi",
                            "TechZone Wholesale",
                            "CoverHub Retail Chain",
                            "Gadget Gallery Pune",
                            "Phone Palace Kolkata",
                        ]
                    ),
                    "sales_rep": rep,
                    "stage": stage,
                    "expected_close_date": (date(2024, random.randint(1, 12), random.randint(1, 28))).isoformat(),
                    "deal_value_inr": amount,
                    "product_focus": random.choice([c[0] for c in CASE_LINES]),
                    "probability_pct": {"Qualified": 20, "Proposal": 45, "Negotiation": 65, "Closed Won": 100, "Closed Lost": 0}[stage],
                }
            )
    _write(pd.DataFrame(pipeline), "03-sales-performance/b2b_pipeline_and_quotas.xlsx")


def generate_campaign_efficiency() -> None:
    camp_rows = []
    cid = 1
    for month in _month_starts(2024, 12):
        for ch in AD_CHANNELS:
            spend = round(random.uniform(25000, 280000) * (1.25 if ch in ("Meta Ads", "Google Ads") else 0.85), 2)
            impressions = int(spend * random.uniform(8, 45))
            clicks = int(impressions * random.uniform(0.008, 0.035))
            conversions = int(clicks * random.uniform(0.02, 0.09))
            revenue = round(conversions * random.uniform(28, 52), 2)
            camp_rows.append(
                {
                    "campaign_name": f"SlickStyles_{ch.replace(' ', '')}_M{month.month:02d}",
                    "channel": ch,
                    "start_date": month.isoformat(),
                    "end_date": (month + timedelta(days=27)).isoformat(),
                    "budget_inr": round(spend * 1.1, 2),
                    "spend_inr": spend,
                    "impressions": impressions,
                    "clicks": clicks,
                    "orders": conversions,
                    "attributed_revenue_inr": revenue,
                    "cpa_inr": round(spend / conversions, 2) if conversions else None,
                    "roas": round(revenue / spend, 2) if spend else None,
                }
            )
            cid += 1
    _write(pd.DataFrame(camp_rows), "04-campaign-efficiency/paid_ads_campaign_performance.xlsx")

    infl_rows = []
    for i in range(24):
        spend = round(random.uniform(15000, 120000), 2)
        orders = int(spend / random.uniform(35, 75))
        infl_rows.append(
            {
                "creator_handle": random.choice(
                    [
                        "@techstyle.in",
                        "@phonefashion",
                        "@casequeen",
                        "@unboxindia",
                        "@gadgetguru",
                    ]
                ),
                "campaign_month": random.choice(_month_starts(2024, 12)).replace(day=1).isoformat(),
                "platform": random.choice(["Instagram", "YouTube", "Affiliate"]),
                "fee_inr": spend,
                "coupon_code": random.choice(["SLICK10", "GRIP15", "MAGSAFE20", "NEWCASE"]),
                "tracked_orders": orders,
                "tracked_revenue_inr": round(orders * random.uniform(24, 42), 2),
                "roas": round(orders * 32 / spend, 2),
            }
        )
    _write(pd.DataFrame(infl_rows), "04-campaign-efficiency/influencer_and_affiliate_performance.xlsx")


def generate_customer_value() -> None:
    customers = []
    for i in range(1, 151):
        signup = date(2022, 1, 1) + timedelta(days=random.randint(0, 900))
        orders = random.randint(1, 48)
        spent = round(sum(random.uniform(18, 55) for _ in range(orders)), 2)
        tier = (
            "Platinum"
            if spent > 12000
            else ("Gold" if spent > 5000 else ("Silver" if spent > 1500 else "Bronze"))
        )
        fav_model = random.choice(PHONE_MODELS)
        customers.append(
            {
                "customer_id": f"SS-C{i:04d}",
                "customer_name": f"Customer {i}",
                "email": f"buyer{i}@example.com",
                "city": random.choice(
                    ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Pune", "Chennai", "Kolkata"]
                ),
                "signup_date": signup.isoformat(),
                "lifetime_spend_inr": spent,
                "order_count": orders,
                "tier": tier,
                "favorite_phone_model": fav_model,
                "preferred_channel": random.choice(CHANNELS),
                "last_order_date": (signup + timedelta(days=random.randint(30, 400))).isoformat(),
            }
        )
    _write(pd.DataFrame(customers), "05-customer-value/customer_account_summary.xlsx")

    cohort_rows = []
    for tier in ["Platinum", "Gold", "Silver", "Bronze"]:
        for month in _month_starts(2024, 12):
            active = int(random.uniform(20, 200) * {"Platinum": 0.4, "Gold": 0.7, "Silver": 1.0, "Bronze": 1.3}[tier])
            repeat = int(active * random.uniform(0.15, 0.45))
            cohort_rows.append(
                {
                    "month": month.replace(day=1).isoformat(),
                    "customer_tier": tier,
                    "active_customers": active,
                    "repeat_purchasers": repeat,
                    "repeat_rate_pct": round(100 * repeat / active, 1) if active else 0,
                    "avg_orders_per_active": round(random.uniform(1.0, 2.4), 2),
                    "segment_revenue_inr": round(repeat * random.uniform(28, 48) * random.uniform(1.2, 2.5), 2),
                }
            )
    _write(pd.DataFrame(cohort_rows), "05-customer-value/repeat_purchase_by_tier.xlsx")


def main() -> None:
    print("Generating Slick Styles demo workbooks…\n")
    print("01 — Monthly business review")
    generate_monthly_business_review()
    print("\n02 — Profit leak audit")
    generate_profit_leak_audit()
    print("\n03 — Sales performance")
    generate_sales_performance()
    print("\n04 — Campaign efficiency")
    generate_campaign_efficiency()
    print("\n05 — Customer value")
    generate_customer_value()
    print("\nDone.")


if __name__ == "__main__":
    main()
