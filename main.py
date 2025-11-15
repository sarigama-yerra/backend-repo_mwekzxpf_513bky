import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Product, CartItem, Order, OrderItem

app = FastAPI(title="E-Commerce API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProductCreate(Product):
    pass

class ProductResponse(Product):
    id: str

class CartItemCreate(CartItem):
    pass

class CartItemResponse(CartItem):
    id: str

class OrderCreate(BaseModel):
    cart_id: str

class OrderResponse(Order):
    id: str


@app.get("/")
def read_root():
    return {"message": "E-Commerce Backend Ready"}


@app.get("/schema")
def get_schema():
    # Simple acknowledgment; platform reads schemas.py directly
    return {"status": "ok"}


# Products
@app.get("/products", response_model=List[ProductResponse])
def list_products(category: Optional[str] = None, q: Optional[str] = None, sort: Optional[str] = None):
    filt = {}
    if category:
        filt["category"] = category
    if q:
        filt["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
        ]
    docs = list(db["product"].find(filt))
    # sorting
    if sort == "price_asc":
        docs.sort(key=lambda d: float(d.get("price", 0)))
    elif sort == "price_desc":
        docs.sort(key=lambda d: float(d.get("price", 0)), reverse=True)
    results: List[ProductResponse] = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        results.append(ProductResponse(**d))
    return results

@app.post("/products", response_model=str)
def create_product(payload: ProductCreate):
    new_id = create_document("product", payload)
    return new_id

@app.get("/categories", response_model=List[str])
def list_categories():
    cats = db["product"].distinct("category")
    cats = [c for c in cats if isinstance(c, str)]
    cats.sort()
    return cats


# Cart
@app.get("/cart/{cart_id}", response_model=List[CartItemResponse])
def get_cart(cart_id: str):
    docs = get_documents("cartitem", {"cart_id": cart_id})
    out: List[CartItemResponse] = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        out.append(CartItemResponse(**d))
    return out

@app.post("/cart", response_model=str)
def add_to_cart(item: CartItemCreate):
    # If item for product already exists in cart, increment quantity
    existing = db["cartitem"].find_one({"cart_id": item.cart_id, "product_id": item.product_id})
    if existing:
        new_qty = int(existing.get("quantity", 1)) + int(item.quantity)
        db["cartitem"].update_one({"_id": existing["_id"]}, {"$set": {"quantity": new_qty}})
        return str(existing["_id"])  # return existing id
    inserted_id = create_document("cartitem", item)
    return inserted_id

@app.delete("/cart/{item_id}")
def remove_from_cart(item_id: str):
    try:
        db["cartitem"].delete_one({"_id": ObjectId(item_id)})
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid item id")


# Orders
@app.post("/orders", response_model=str)
def create_order(payload: OrderCreate):
    # Build order items from cart
    cart_docs = get_documents("cartitem", {"cart_id": payload.cart_id})
    if not cart_docs:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Fetch product details
    items: List[OrderItem] = []
    subtotal = 0.0
    for ci in cart_docs:
        prod = db["product"].find_one({"_id": ObjectId(ci["product_id"])})
        if not prod:
            continue
        qty = int(ci.get("quantity", 1))
        price = float(prod.get("price", 0))
        subtotal += price * qty
        items.append(OrderItem(product_id=str(prod["_id"]), title=prod.get("title", ""), price=price, quantity=qty))

    tax = round(subtotal * 0.07, 2)
    total = round(subtotal + tax, 2)

    order = Order(cart_id=payload.cart_id, items=items, subtotal=round(subtotal, 2), tax=tax, total=total)
    order_id = create_document("order", order)

    # Clear cart
    db["cartitem"].delete_many({"cart_id": payload.cart_id})

    return order_id

@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str):
    try:
        doc = db["order"].find_one({"_id": ObjectId(order_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Order not found")
        doc["id"] = str(doc.pop("_id"))
        # Pydantic validation
        return OrderResponse(**doc)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid order id")


# Seed demo electronics catalog
@app.post("/seed/electronics")
def seed_electronics():
    demo_products = [
        {
            "title": "Pro Series 55\" 4K UHD Smart TV",
            "description": "Ultra-thin bezel, HDR10+, Dolby Vision, 120Hz.",
            "price": 599.99,
            "category": "tv",
            "image": "https://images.unsplash.com/photo-1593359677879-38f8b1ba30c3?q=80&w=1200&auto=format&fit=crop"
        },
        {
            "title": "Aurora X1 Gaming Laptop (RTX 4070, 16GB, 1TB)",
            "description": "14-core CPU, QHD 165Hz display, per-key RGB.",
            "price": 1699.0,
            "category": "laptop",
            "image": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?q=80&w=1200&auto=format&fit=crop"
        },
        {
            "title": "PixelWave Pro Smartphone",
            "description": "6.7\" OLED 120Hz, triple camera with 5x telephoto.",
            "price": 999.0,
            "category": "phone",
            "image": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?q=80&w=1200&auto=format&fit=crop"
        },
        {
            "title": "Nimbus ANC Wireless Headphones",
            "description": "Adaptive noise cancelling, 40h battery, LDAC.",
            "price": 249.0,
            "category": "audio",
            "image": "https://images.unsplash.com/photo-1518444028785-8fce0a366e2f?q=80&w=1200&auto=format&fit=crop"
        },
        {
            "title": "IonCharge 65W GaN USB-C Charger",
            "description": "Dual USB-C PD, foldable prongs, travel-ready.",
            "price": 39.99,
            "category": "accessories",
            "image": "https://images.unsplash.com/photo-1587825140400-67bc116ed27b?q=80&w=1200&auto=format&fit=crop"
        },
        {
            "title": "Velocity Series Mechanical Keyboard",
            "description": "Hot-swappable switches, aluminum frame, tri-mode.",
            "price": 139.0,
            "category": "gaming",
            "image": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?q=80&w=1200&auto=format&fit=crop"
        },
        {
            "title": "HyperSound 2.1 Bluetooth Soundbar",
            "description": "Wireless subwoofer, HDMI eARC, virtual surround.",
            "price": 299.0,
            "category": "audio",
            "image": "https://images.unsplash.com/photo-1616348436168-de43ad0db179?q=80&w=1200&auto=format&fit=crop"
        }
    ]

    inserted = 0
    for p in demo_products:
        # Idempotent: avoid duplicates by matching title
        exists = db["product"].find_one({"title": p["title"]})
        if not exists:
            create_document("product", Product(**p))
            inserted += 1
    return {"inserted": inserted, "total": len(demo_products)}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
