import os
import re
import secrets
from datetime import datetime, timezone
from functools import wraps

from bson.errors import InvalidId
from bson.objectid import ObjectId
from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, session, url_for)
from pymongo import DESCENDING, MongoClient
from pymongo.errors import PyMongoError

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000)
records = client[os.getenv("DB_NAME", "dataentry")]["inquiries"]

COMPANY = {
    "name": os.getenv("COMPANY_NAME", "MishaIQ"),
    "email": os.getenv("COMPANY_EMAIL", "hello@mishaiq.example"),
    "phone": os.getenv("COMPANY_PHONE", "+00 000 000 0000"),
    "address": os.getenv("COMPANY_ADDRESS", "Your office address, City, Country"),
}
SERVICES = [
    ("Cloud migration", "Move workloads to AWS, Azure or GCP with a tested cutover plan."),
    ("Managed support", "Round-the-clock monitoring and incident response for production systems."),
    ("DevOps automation", "CI/CD pipelines, infrastructure as code and repeatable releases."),
    ("Security and compliance", "Access control, audits and hardening that stand up to review."),
]
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def csrf():
    session.setdefault("csrf", secrets.token_hex(16))
    return session["csrf"]


app.jinja_env.globals.update(csrf=csrf, company=COMPANY, services=SERVICES)


def same(a, b):
    return secrets.compare_digest((a or "").encode(), (b or "").encode())


def admin_only(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or not (same(auth.username, ADMIN_USER) and same(auth.password, ADMIN_PASSWORD)):
            return Response("Sign in required.", 401, {"WWW-Authenticate": 'Basic realm="Admin"'})
        return view(*args, **kwargs)
    return wrapper


def validate(form):
    d = {k: form.get(k, "").strip() for k in ("name", "email", "phone", "company", "service", "message")}
    e = {}
    if not d["name"]:
        e["name"] = "Enter your full name."
    if not d["email"]:
        e["email"] = "Enter your work email."
    elif not EMAIL_RE.match(d["email"]):
        e["email"] = "Enter an email like name@company.com."
    if d["phone"] and not re.fullmatch(r"[0-9+()\-\s]{7,20}", d["phone"]):
        e["phone"] = "Use digits, spaces, + or - only."
    if d["service"] not in [s[0] for s in SERVICES]:
        e["service"] = "Choose the service you need."
    if not d["message"]:
        e["message"] = "Tell us briefly what you need."
    if any(len(v) > (2000 if k == "message" else 120) for k, v in d.items()):
        e["message"] = "That is too long. Keep it under 2000 characters."
    return d, e


@app.route("/", methods=["GET", "POST"])
def index():
    values, errors = {}, {}
    if request.method == "POST":
        if request.form.get("website"):  # honeypot: bots fill this hidden field
            return redirect(url_for("index"))
        values, errors = validate(request.form)
        if not errors:
            try:
                records.insert_one({**values, "created_at": datetime.now(timezone.utc)})
            except PyMongoError:
                errors["form"] = "We could not save your request. Please try again in a minute."
            else:
                session["sent"] = {"name": values["name"].split()[0], "email": values["email"]}
                return redirect(url_for("index") + "#contact")
    return render_template("index.html", values=values, errors=errors,
                           sent=session.pop("sent", None), status=400 if errors else 200), (400 if errors else 200)


@app.route("/admin")
@admin_only
def admin():
    rows = list(records.find().sort("created_at", DESCENDING))
    for r in rows:
        r["id"] = str(r["_id"])
        r["when"] = r["created_at"].strftime("%d %b %Y, %H:%M UTC")
    return render_template("admin.html", rows=rows)


@app.route("/admin/delete/<rid>", methods=["POST"])
@admin_only
def delete(rid):
    if not same(request.form.get("csrf"), session.get("csrf")):
        abort(400)
    try:
        records.delete_one({"_id": ObjectId(rid)})
    except (InvalidId, PyMongoError):
        abort(400)
    return redirect(url_for("admin"))


@app.route("/api/records")
@admin_only
def api_records():
    out = []
    for r in records.find().sort("created_at", DESCENDING):
        r["_id"] = str(r["_id"])
        r["created_at"] = r["created_at"].isoformat()
        out.append(r)
    return jsonify(out)


@app.route("/health")
def health():
    try:
        client.admin.command("ping")
        return jsonify(status="ok")
    except PyMongoError:
        return jsonify(status="db unavailable"), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
