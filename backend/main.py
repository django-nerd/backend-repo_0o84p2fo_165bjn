from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from schemas import Review
from database import db, create_document, get_documents
from bson import ObjectId
from passlib.context import CryptContext

app = FastAPI(title="Grahini Ghee API")

# CORS to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin auth (simple email/password stored in DB)
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Admin(BaseModel):
    email: str
    password: str


async def ensure_default_admin():
    # Create default admin if not exists
    collection = db["admin"]
    existing = await collection.find_one({"email": "admin@grahini.in"})
    if not existing:
        hashed = pwd_ctx.hash("grahini123")
        await collection.insert_one({
            "email": "admin@grahini.in",
            "password": hashed,
            "created_at": datetime.utcnow(),
        })


@app.on_event("startup")
async def on_startup():
    await ensure_default_admin()


# Public endpoints
@app.get("/", tags=["public"])
async def root():
    return {"message": "Grahini Ghee API running"}


@app.get("/reviews", response_model=List[dict], tags=["public"])
async def get_approved_reviews(limit: int = 50):
    # Only approved reviews
    items = await get_documents("review", {"approved": True}, limit)
    # Convert ObjectId to str
    for it in items:
        if isinstance(it.get("_id"), ObjectId):
            it["id"] = str(it.pop("_id"))
    return items


@app.post("/reviews", status_code=201, tags=["public"])
async def submit_review(review: Review):
    # New reviews are unapproved by default (enforced in schema)
    data = review.dict()
    data["approved"] = False
    await create_document("review", data)
    return {"success": True, "message": "Review submitted for approval"}


# Admin models and endpoints
class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str


# super simple token store in memory would be disallowed; we'll use a small collection
@app.post("/admin/login", response_model=LoginResponse, tags=["admin"])
async def admin_login(payload: LoginRequest):
    coll = db["admin"]
    admin = await coll.find_one({"email": payload.email})
    if not admin or not pwd_ctx.verify(payload.password, admin["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = pwd_ctx.hash(admin["email"] + str(datetime.utcnow()))
    await db["tokens"].insert_one({
        "token": token,
        "email": admin["email"],
        "created_at": datetime.utcnow(),
    })
    return LoginResponse(token=token)


async def get_admin_email_from_token(token: str) -> str:
    rec = await db["tokens"].find_one({"token": token})
    if not rec:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return rec["email"]


class ApproveRequest(BaseModel):
    review_id: str
    approved: bool


@app.get("/admin/reviews", tags=["admin"])
async def list_pending_reviews(token: str, include_all: Optional[bool] = False):
    await get_admin_email_from_token(token)
    filt = {} if include_all else {"approved": False}
    items = await get_documents("review", filt, 200)
    for it in items:
        if isinstance(it.get("_id"), ObjectId):
            it["id"] = str(it.pop("_id"))
    return items


@app.post("/admin/reviews/approve", tags=["admin"])
async def approve_review(payload: ApproveRequest, token: str):
    await get_admin_email_from_token(token)
    try:
        oid = ObjectId(payload.review_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid review id")
    coll = db["review"]
    res = await coll.update_one({"_id": oid}, {"$set": {"approved": payload.approved}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"success": True}


# Simple health check for DB
@app.get("/test", tags=["public"])
async def test_db():
    # Try inserting a tiny doc and reading it back using helpers
    await create_document("ping", {"msg": "ok"})
    docs = await get_documents("ping", {}, 1)
    return {"ok": True, "count": len(docs)}
