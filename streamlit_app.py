import os
import requests
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

# BASE_URL = "https://uos-stockpilot.onrender.com"

BASE_URL = (
    os.getenv("API_BASE_URL")
    or st.secrets.get("API_BASE_URL")
    or "http://127.0.0.1:8000"
)

SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_ANON_KEY = (
    os.getenv("SUPABASE_ANON_KEY")
    or st.secrets.get("SUPABASE_ANON_KEY")
)

PRODUCT_OPTIONS = {
    "UoS Classic Mug": 1,
    "UoS Graduation Mug": 2,
    "UoS Alumni Mug": 3,
    "UoS Sports Mug": 4,
    "UoS Limited Edition Mug": 5,
}

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")

st.set_page_config(
    page_title="UoS StockPilot",
    page_icon="📦",
    layout="wide"
)

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("Missing SUPABASE_URL or SUPABASE_ANON_KEY in .env file.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ---------- Styling ----------
st.markdown(
    """
    <style>
        .main-title {
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .sub-title {
            color: #555;
            margin-bottom: 1.2rem;
        }
        .kpi-card {
            background-color: #ffffff;
            padding: 1rem;
            border-radius: 14px;
            border: 1px solid #e6e6e6;
            box-shadow: 0 2px 10px rgba(0,0,0,0.04);
            text-align: center;
            min-height: 120px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .kpi-label {
            font-size: 0.95rem;
            color: #666;
            margin-bottom: 0.35rem;
        }
        .kpi-value {
            font-size: 1.8rem;
            font-weight: 700;
            color: #111;
        }
        .brand-box {
            background: linear-gradient(135deg, #facc15, #eab308);
            color: #111;
            padding: 1rem 1rem;
            border-radius: 14px;
            margin-bottom: 1rem;
        }
        .small-note {
            color: #666;
            font-size: 0.9rem;
        }
        .login-container {
            max-width: 420px;
            margin: 80px auto 20px auto;
            padding: 2rem;
            border-radius: 16px;
            border: 1px solid #e6e6e6;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
            background-color: white;
        }
        .login-title {
            font-size: 2rem;
            font-weight: 700;
            color: #facc15;
            margin-bottom: 0.3rem;
            text-align: center;
        }
        .login-subtitle {
            color: #555;
            text-align: center;
            margin-bottom: 1.5rem;
        }
        div.stButton > button {
            border-radius: 8px;
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------- Helpers ----------
def get_inventory(product_id: int):
    response = requests.get(f"{BASE_URL}/inventory/{product_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def get_forecast(product_id: int):
    response = requests.get(f"{BASE_URL}/forecast/{product_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def generate_recommendation(product_id: int):
    response = requests.post(f"{BASE_URL}/recommendation/{product_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def get_recommendations(product_id: int):
    response = requests.get(f"{BASE_URL}/recommendations/{product_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def get_audit_logs():
    response = requests.get(f"{BASE_URL}/audit-logs", timeout=10)
    response.raise_for_status()
    return response.json()


def update_inventory_directly(
    product_id: int,
    current_stock: int,
    safety_stock: int,
    lead_time_days: int,
    auto_reorder: bool,
):
    payload = {
        "current_stock": current_stock,
        "safety_stock": safety_stock,
        "lead_time_days": lead_time_days,
        "auto_reorder": auto_reorder,
    }
    response = requests.patch(
        f"{BASE_URL}/inventory/{product_id}",
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def run_auto_order(product_id: int):
    response = requests.post(f"{BASE_URL}/auto-order/{product_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def get_sales_debug(product_id: int):
    response = requests.get(f"{BASE_URL}/debug/sales/{product_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def login_user(email: str, password: str):
    return supabase.auth.sign_in_with_password(
        {
            "email": email,
            "password": password,
        }
    )


def logout_user():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass


def render_kpi(label: str, value):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_datetime_column(df: pd.DataFrame, column_name: str, fmt: str):
    if column_name in df.columns:
        df[column_name] = pd.to_datetime(df[column_name]).dt.strftime(fmt)
    return df


# ---------- Session state ----------
if "latest_recommendation" not in st.session_state:
    st.session_state.latest_recommendation = None

if "latest_auto_order" not in st.session_state:
    st.session_state.latest_auto_order = None

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "user_email" not in st.session_state:
    st.session_state.user_email = None

# ---------- Login Gate ----------
if not st.session_state.authenticated:
    st.markdown(
        """
        <div class="login-container">
            <div class="login-title">UoS StockPilot</div>
            <div class="login-subtitle">
                Secure warehouse stock forecasting and replenishment
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left_col, center_col, right_col = st.columns([1, 2, 1])

    with center_col:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            login_submitted = st.form_submit_button("Sign In", use_container_width=True)

            if login_submitted:
                try:
                    auth_response = login_user(email, password)

                    if auth_response and getattr(auth_response, "user", None):
                        st.session_state.authenticated = True
                        st.session_state.user_email = auth_response.user.email
                        st.success("Login successful.")
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")
                except Exception as exc:
                    st.error(f"Login failed: {exc}")

    st.stop()

# ---------- Sidebar ----------
st.sidebar.markdown(
    """
    <div class="brand-box">
        <div style="font-size:1.25rem;font-weight:700;">UoS StockPilot</div>
        <div style="font-size:0.95rem;opacity:0.9;">Smart Inventory Forecasting</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.session_state.user_email:
    st.sidebar.caption(f"Signed in as: {st.session_state.user_email}")

selected_product_name = st.sidebar.selectbox(
    "Select Product",
    list(PRODUCT_OPTIONS.keys()),
    key="product_selector",
)

PRODUCT_ID = PRODUCT_OPTIONS[selected_product_name]

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Inventory", "Recommendations", "Audit Logs"],
    key="main_navigation_radio",
)

st.sidebar.markdown("---")
st.sidebar.info(f"Product: {selected_product_name}")

sidebar_col1, sidebar_col2 = st.sidebar.columns(2)

with sidebar_col1:
    if st.button("Refresh App", use_container_width=True, key="refresh_app_button"):
        st.rerun()

with sidebar_col2:
    if st.button("Logout", use_container_width=True, key="logout_button"):
        logout_user()
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.latest_recommendation = None
        st.session_state.latest_auto_order = None
        st.rerun()

# ---------- Dashboard ----------
if page == "Dashboard":
    st.markdown('<div class="main-title">Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="sub-title">Monitor stock, forecast demand, and automate replenishment for <strong>{selected_product_name}</strong>.</div>',
        unsafe_allow_html=True,
    )

    try:
        inventory = get_inventory(PRODUCT_ID)
        forecast = get_forecast(PRODUCT_ID)

        reorder_point = round(
            forecast["forecast_daily_demand"] * inventory["lead_time_days"] + inventory["safety_stock"],
            2,
        )
        risk_status = "High Risk" if inventory["current_stock"] <= reorder_point else "Safe"

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            render_kpi("Current Stock", inventory["current_stock"])
        with kpi2:
            render_kpi("Safety Stock", inventory["safety_stock"])
        with kpi3:
            render_kpi("Lead Time (Days)", inventory["lead_time_days"])
        with kpi4:
            render_kpi("Forecast / Day", forecast["forecast_daily_demand"])

        st.markdown("")

        if risk_status == "High Risk":
            st.error(
                f"Stock Risk: {risk_status} — current stock is below the calculated reorder point of {reorder_point}."
            )
        else:
            st.success(
                f"Stock Risk: {risk_status} — current stock is above the calculated reorder point of {reorder_point}."
            )

        left_panel, right_panel = st.columns([1.2, 1])

        with left_panel:
            st.subheader("AI Replenishment Recommendation")
            st.write(
                "Generate an order recommendation based on recent demand, lead time, and safety stock."
            )

            btn1, btn2 = st.columns(2)

            with btn1:
                if st.button(
                    "Generate Recommendation",
                    type="primary",
                    use_container_width=True,
                    key=f"generate_recommendation_button_{PRODUCT_ID}",
                ):
                    st.session_state.latest_recommendation = generate_recommendation(PRODUCT_ID)
                    st.session_state.latest_auto_order = None

            with btn2:
                if st.button(
                    "Run Auto Reorder Check",
                    use_container_width=True,
                    key=f"run_auto_reorder_button_{PRODUCT_ID}",
                ):
                    st.session_state.latest_auto_order = run_auto_order(PRODUCT_ID)

            if st.session_state.latest_recommendation:
                result = st.session_state.latest_recommendation
                st.markdown("---")
                st.subheader("Recommendation Result")

                rec1, rec2, rec3 = st.columns(3)
                with rec1:
                    st.metric("Reorder Point", result["reorder_point"])
                with rec2:
                    st.metric("Recommended Qty", result["recommended_qty"])
                with rec3:
                    st.metric("Current Stock", result["current_stock"])

                if "seasonal_factor" in result:
                    st.write(f"**Seasonal Factor Applied:** {result['seasonal_factor']}")

                st.info(result["reason"])

        with right_panel:
            st.subheader("Operational Summary")
            st.write(f"**Product:** {selected_product_name}")
            st.write(f"**Auto Reorder Enabled:** {'Yes' if inventory['auto_reorder'] else 'No'}")
            st.write(f"**Calculated Reorder Point:** {reorder_point}")
            st.write(f"**Demand Basis:** Last {forecast['based_on_days']} days")

            if "base_forecast" in forecast:
                st.write(f"**Base Forecast:** {forecast['base_forecast']}")

            if "seasonal_factor" in forecast:
                st.write(f"**Seasonal Factor:** {forecast['seasonal_factor']}")

            st.write(f"**Adjusted Forecast:** {forecast['forecast_daily_demand']}")
            
            if inventory["auto_reorder"]:
                st.success("Automation is enabled for this product.")
            else:
                st.info("Automation is currently disabled. Recommendations remain manual.")

            st.markdown(
                '<div class="small-note">This recommendation engine helps warehouse staff avoid stockouts while reducing manual intervention.</div>',
                unsafe_allow_html=True,
            )

        if st.session_state.latest_auto_order:
            auto = st.session_state.latest_auto_order
            st.markdown("---")
            st.subheader("Auto Order Result")

            message = auto.get("message", "Auto order processed.")

            if "disabled" in message.lower():
                st.warning(message)
            elif "successfully" in message.lower():
                st.success(message)
            elif "no order created" in message.lower():
                st.info(message)
            else:
                st.write(message)

            auto_col1, auto_col2 = st.columns(2)
            with auto_col1:
                if "recommended_qty" in auto:
                    st.metric("Recommended Qty", auto["recommended_qty"])
            with auto_col2:
                if "reorder_point" in auto:
                    st.metric("Reorder Point", auto["reorder_point"])

            if "seasonal_factor" in auto:
                st.write(f"**Seasonal Factor Applied:** {auto['seasonal_factor']}")

        st.markdown("### Recent Sales Trend")
        try:
            sales_data = get_sales_debug(PRODUCT_ID).get("sales_rows", [])

            if sales_data:
                sales_df = pd.DataFrame(sales_data)
                sales_df["date"] = pd.to_datetime(sales_df["date"])
                sales_df = sales_df.sort_values("date")

                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(sales_df["date"], sales_df["units_sold"], marker="o")
                ax.set_xlabel("Date")
                ax.set_ylabel("Units Sold")
                ax.set_title(f"Recent Demand — {selected_product_name}")
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.warning("No sales trend data available.")
        except Exception as exc:
            st.warning(f"Could not load sales chart: {exc}")

        st.markdown("### Recent Recommendations")
        recs = get_recommendations(PRODUCT_ID)
        rec_list = recs.get("recommendations", [])

        if rec_list:
            df = pd.DataFrame(rec_list)
            show_cols = [col for col in ["created_at", "recommended_qty", "reason"] if col in df.columns]
            display_df = df[show_cols].copy()
            display_df = format_datetime_column(display_df, "created_at", "%Y-%m-%d %H:%M")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No recommendations found yet.")

    except Exception as exc:
        st.error(f"Error loading dashboard: {exc}")

# ---------- Inventory ----------
elif page == "Inventory":
    st.markdown('<div class="main-title">Inventory Settings</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="sub-title">Update stock, safety stock, lead time, and auto reorder settings for <strong>{selected_product_name}</strong>.</div>',
        unsafe_allow_html=True,
    )

    try:
        inventory = get_inventory(PRODUCT_ID)
        forecast = get_forecast(PRODUCT_ID)

        if not inventory:
            st.warning("No inventory record found for the selected product yet.")
            st.stop()

        # Top KPI row
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            render_kpi("Current Stock", inventory["current_stock"])
        with kpi2:
            render_kpi("Safety Stock", inventory["safety_stock"])
        with kpi3:
            render_kpi("Lead Time (Days)", inventory["lead_time_days"])
        with kpi4:
            render_kpi("Auto Reorder", "On" if inventory["auto_reorder"] else "Off")

        st.markdown("")

        # Forecast explanation row
        if forecast:
            fx1, fx2, fx3 = st.columns(3)
            with fx1:
                render_kpi("Base Forecast", forecast.get("base_forecast", "N/A"))
            with fx2:
                render_kpi("Seasonal Factor", forecast.get("seasonal_factor", "N/A"))
            with fx3:
                render_kpi("Adjusted Forecast", forecast.get("forecast_daily_demand", "N/A"))

            st.markdown("")
        else:
            st.info("No sales history is available yet for this product, so forecast details cannot be shown.")

        st.markdown("### Update Inventory")

        with st.form(f"inventory_form_{PRODUCT_ID}"):
            form_col1, form_col2 = st.columns(2)

            with form_col1:
                current_stock = st.number_input(
                    "Current Stock",
                    min_value=0,
                    value=int(inventory["current_stock"]),
                    step=1,
                )

                safety_stock = st.number_input(
                    "Safety Stock",
                    min_value=0,
                    value=int(inventory["safety_stock"]),
                    step=1,
                )

            with form_col2:
                lead_time_days = st.number_input(
                    "Lead Time (Days)",
                    min_value=1,
                    value=int(inventory["lead_time_days"]),
                    step=1,
                )

                auto_reorder = st.checkbox(
                    "Enable Auto Reorder",
                    value=bool(inventory["auto_reorder"]),
                    key=f"auto_reorder_checkbox_{PRODUCT_ID}",
                )

            submitted = st.form_submit_button(
                "Save Inventory Settings",
                use_container_width=True,
            )

            if submitted:
                try:
                    update_inventory_directly(
                        product_id=PRODUCT_ID,
                        current_stock=current_stock,
                        safety_stock=safety_stock,
                        lead_time_days=lead_time_days,
                        auto_reorder=auto_reorder,
                    )
                    st.success("Inventory updated successfully.")
                    st.write(
                        "The inventory settings have been saved and will now be used for future recommendations and auto-reorder checks."
                    )
                except Exception as exc:
                    st.error(f"Could not update inventory: {exc}")

    except Exception as exc:
        st.error(f"Error loading inventory: {exc}")
        
# ---------- Recommendations ----------
elif page == "Recommendations":
    st.markdown('<div class="main-title">Recommendation History</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="sub-title">Review previously generated stock recommendations for <strong>{selected_product_name}</strong>.</div>',
        unsafe_allow_html=True,
    )

    try:
        recs = get_recommendations(PRODUCT_ID)
        rec_list = recs.get("recommendations", [])

        if rec_list:
            df = pd.DataFrame(rec_list)
            show_cols = [col for col in ["created_at", "recommended_qty", "reason"] if col in df.columns]
            display_df = df[show_cols].copy()
            display_df = format_datetime_column(display_df, "created_at", "%Y-%m-%d %H:%M")
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.markdown("### Recommendation Volume")
            chart_df = df.copy()
            if "created_at" in chart_df.columns and "recommended_qty" in chart_df.columns:
                chart_df["created_at"] = pd.to_datetime(chart_df["created_at"])
                chart_df = chart_df.sort_values("created_at")

                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(chart_df["created_at"], chart_df["recommended_qty"], marker="o")
                ax.set_xlabel("Created At")
                ax.set_ylabel("Recommended Qty")
                ax.set_title(f"Recommendation Trend — {selected_product_name}")
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
        else:
            st.warning("No recommendations available yet.")

        if st.button("Refresh Recommendations", key=f"refresh_recommendations_button_{PRODUCT_ID}"):
            st.rerun()

    except Exception as exc:
        st.error(f"Error loading recommendations: {exc}")

# ---------- Audit Logs ----------
elif page == "Audit Logs":
    st.markdown('<div class="main-title">Audit Logs</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-title">Track system activity, inventory changes, and automated decisions.</div>',
        unsafe_allow_html=True,
    )

    try:
        logs = get_audit_logs().get("audit_logs", [])

        if logs:
            df = pd.DataFrame(logs)

            # optional filter by selected product id if mentioned in action text
            filtered_df = df[df["action"].astype(str).str.contains(f"product {PRODUCT_ID}", case=False, na=False)].copy()

            if filtered_df.empty:
                st.info("No audit logs found yet for the selected product.")
            else:
                show_cols = [col for col in ["created_at", "action"] if col in filtered_df.columns]
                display_df = filtered_df[show_cols].copy()
                display_df = format_datetime_column(display_df, "created_at", "%Y-%m-%d %H:%M:%S")
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                st.metric("Total Logged Events", len(display_df))
        else:
            st.warning("No audit logs available yet.")

        if st.button("Refresh Logs", key=f"refresh_logs_button_{PRODUCT_ID}"):
            st.rerun()

    except Exception as exc:
        st.error(f"Error loading audit logs: {exc}")