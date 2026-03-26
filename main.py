from datetime import datetime
import math
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import Client, create_client


class InventoryUpdate(BaseModel):
    current_stock: int
    safety_stock: int
    lead_time_days: int
    auto_reorder: bool


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="UoS StockPilot API")


@app.get("/")
def root():
    return {"message": "UoS StockPilot API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


def get_recent_sales(product_id: int):
    response = (
        supabase.table("sales_history")
        .select("*")
        .eq("product_id", product_id)
        .order("date", desc=False)
        .execute()
    )
    return response.data


def get_inventory(product_id: int):
    response = (
        supabase.table("inventory")
        .select("*")
        .eq("product_id", product_id)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def create_audit_log(action: str, user_id=None):
    response = (
        supabase.table("audit_logs")
        .insert(
            {
                "action": action,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )
    return response.data


def calculate_forecast(sales_rows: list) -> float:
    if not sales_rows:
        return 0.0

    sales_values = [row["units_sold"] for row in sales_rows[-7:]]
    avg_daily_demand = sum(sales_values) / len(sales_values)

    return round(avg_daily_demand, 2)


def get_seasonal_factor(product_id: int) -> float:
    today = datetime.utcnow()
    current_month = today.month
    current_weekday = today.weekday()  # Monday=0, Sunday=6

    # UoS Classic Mug: term-start demand uplift
    if product_id == 1:
        if current_month in [9, 10]:
            return 1.2

    # UoS Graduation Mug: graduation season uplift
    elif product_id == 2:
        if current_month in [6, 7]:
            return 1.5

    # UoS Alumni Mug: alumni activity / summer events uplift
    elif product_id == 3:
        if current_month in [5, 6, 7]:
            return 1.25

    # UoS Sports Mug: weekend uplift
    elif product_id == 4:
        if current_weekday in [5, 6]:
            return 1.4

    # UoS Limited Edition Mug: year-end / festive demand uplift
    elif product_id == 5:
        if current_month in [11, 12]:
            return 1.3

    return 1.0


def calculate_recommendation(
    current_stock: int,
    forecast: float,
    lead_time_days: int,
    safety_stock: int,
):
    reorder_point = (forecast * lead_time_days) + safety_stock

    if current_stock <= reorder_point:
        target_stock = forecast * 14
        recommended_qty = max(math.ceil(target_stock - current_stock), 0)
        reason = (
            f"Current stock ({current_stock}) is at or below reorder point "
            f"({round(reorder_point, 2)}). Recommended reorder based on 14-day target stock."
        )
    else:
        recommended_qty = 0
        reason = (
            f"Current stock ({current_stock}) is above reorder point "
            f"({round(reorder_point, 2)}). No reorder needed now."
        )

    return {
        "forecast_daily_demand": forecast,
        "reorder_point": round(reorder_point, 2),
        "recommended_qty": recommended_qty,
        "reason": reason,
    }


@app.get("/forecast/{product_id}")
def forecast(product_id: int):
    sales_rows = get_recent_sales(product_id)

    if not sales_rows:
        raise HTTPException(
            status_code=404,
            detail="No sales history found for this product",
        )

    base_forecast = calculate_forecast(sales_rows)
    seasonal_factor = get_seasonal_factor(product_id)
    forecast_value = round(base_forecast * seasonal_factor, 2)

    return {
        "product_id": product_id,
        "forecast_daily_demand": forecast_value,
        "base_forecast": base_forecast,
        "seasonal_factor": seasonal_factor,
        "based_on_days": min(len(sales_rows), 7),
    }


@app.post("/recommendation/{product_id}")
def generate_recommendation(product_id: int):
    sales_rows = get_recent_sales(product_id)
    inventory = get_inventory(product_id)

    if not sales_rows:
        raise HTTPException(
            status_code=404,
            detail="No sales history found for this product",
        )

    if not inventory:
        raise HTTPException(
            status_code=404,
            detail="Inventory record not found for this product",
        )

    base_forecast = calculate_forecast(sales_rows)
    seasonal_factor = get_seasonal_factor(product_id)
    forecast_value = round(base_forecast * seasonal_factor, 2)

    result = calculate_recommendation(
        current_stock=inventory["current_stock"],
        forecast=forecast_value,
        lead_time_days=inventory["lead_time_days"],
        safety_stock=inventory["safety_stock"],
    )

    insert_response = (
        supabase.table("recommendations")
        .insert(
            {
                "product_id": product_id,
                "recommended_qty": result["recommended_qty"],
                "reason": result["reason"],
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )

    create_audit_log(
        action=(
            f"Generated recommendation for product {product_id} "
            f"with quantity {result['recommended_qty']}"
        )
    )

    return {
        "product_id": product_id,
        "current_stock": inventory["current_stock"],
        "lead_time_days": inventory["lead_time_days"],
        "safety_stock": inventory["safety_stock"],
        "base_forecast": base_forecast,
        "seasonal_factor": seasonal_factor,
        **result,
        "saved_recommendation": insert_response.data,
    }


@app.post("/auto-order/{product_id}")
def auto_order(product_id: int):
    inventory = get_inventory(product_id)

    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory record not found")

    if not inventory["auto_reorder"]:
        create_audit_log(
            action=f"Auto order attempted for product {product_id} but auto reorder is disabled"
        )
        return {
            "product_id": product_id,
            "message": "Auto reorder is disabled for this product",
        }

    sales_rows = get_recent_sales(product_id)

    if not sales_rows:
        raise HTTPException(status_code=404, detail="No sales history found")

    base_forecast = calculate_forecast(sales_rows)
    seasonal_factor = get_seasonal_factor(product_id)
    forecast_value = round(base_forecast * seasonal_factor, 2)

    result = calculate_recommendation(
        current_stock=inventory["current_stock"],
        forecast=forecast_value,
        lead_time_days=inventory["lead_time_days"],
        safety_stock=inventory["safety_stock"],
    )

    if result["recommended_qty"] <= 0:
        create_audit_log(
            action=f"Auto order checked for product {product_id} but no reorder was needed"
        )
        return {
            "product_id": product_id,
            "message": "No order created because no reorder is needed",
            "base_forecast": base_forecast,
            "seasonal_factor": seasonal_factor,
            **result,
        }

    order_response = (
        supabase.table("orders")
        .insert(
            {
                "product_id": product_id,
                "quantity": result["recommended_qty"],
                "source": "auto",
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )

    create_audit_log(
        action=(
            f"Created auto order for product {product_id} "
            f"with quantity {result['recommended_qty']}"
        )
    )

    return {
        "product_id": product_id,
        "message": "Auto order created successfully",
        "order": order_response.data,
        "base_forecast": base_forecast,
        "seasonal_factor": seasonal_factor,
        **result,
    }


@app.get("/debug/sales/{product_id}")
def debug_sales(product_id: int):
    sales_rows = get_recent_sales(product_id)
    return {"product_id": product_id, "sales_rows": sales_rows}


@app.get("/inventory/{product_id}")
def read_inventory(product_id: int):
    inventory = get_inventory(product_id)

    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory record not found")

    return inventory


@app.patch("/inventory/{product_id}")
def update_inventory(product_id: int, payload: InventoryUpdate):
    existing = get_inventory(product_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Inventory record not found")

    response = (
        supabase.table("inventory")
        .update(
            {
                "current_stock": payload.current_stock,
                "safety_stock": payload.safety_stock,
                "lead_time_days": payload.lead_time_days,
                "auto_reorder": payload.auto_reorder,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        .eq("product_id", product_id)
        .execute()
    )

    create_audit_log(
        action=(
            f"Updated inventory for product {product_id}: "
            f"stock={payload.current_stock}, "
            f"safety_stock={payload.safety_stock}, "
            f"lead_time_days={payload.lead_time_days}, "
            f"auto_reorder={payload.auto_reorder}"
        )
    )

    return {
        "message": "Inventory updated successfully",
        "data": response.data,
    }


@app.get("/recommendations/{product_id}")
def get_recommendations(product_id: int):
    response = (
        supabase.table("recommendations")
        .select("*")
        .eq("product_id", product_id)
        .order("created_at", desc=True)
        .execute()
    )
    return {
        "product_id": product_id,
        "recommendations": response.data,
    }


@app.get("/audit-logs")
def get_audit_logs():
    response = (
        supabase.table("audit_logs")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return {"audit_logs": response.data}