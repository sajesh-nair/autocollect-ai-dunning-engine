import io
import os
import smtplib
from email.mime.text import MIMEText

import joblib
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="AutoCollect OS Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Static UI
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Load Stage 1 Classifier Only
classifier = joblib.load("models/stage_1_classifier.pkl")


class EmailRequest(BaseModel):
    recipient: str
    subject: str
    body: str


@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/process-data")
async def process_data(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))

        # Date Conversions
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
        df["DueDate"] = pd.to_datetime(df["DueDate"], errors="coerce")
        df["PaperlessDate"] = pd.to_datetime(
            df["PaperlessDate"], errors="coerce"
        )

        # Feature Engineering (Exact Stage 1 features)
        df["invoice_month"] = df["InvoiceDate"].dt.month.fillna(1).astype(int)
        df["invoice_dayofweek"] = (
            df["InvoiceDate"].dt.dayofweek.fillna(0).astype(int)
        )
        df["payment_terms_days"] = (
            (df["DueDate"] - df["InvoiceDate"]).dt.days.fillna(0).astype(int)
        )
        df["days_since_paperless"] = (
            (df["InvoiceDate"] - df["PaperlessDate"])
            .dt.days.fillna(0)
            .astype(int)
        )

        # Stage 1: Classifier Inference
        try:
            df["is_delayed"] = classifier.predict(df)
            if hasattr(classifier, "predict_proba"):
                df["risk_score"] = classifier.predict_proba(df)[:, 1]
            else:
                df["risk_score"] = df["is_delayed"].astype(float)
        except Exception:
            # Fallback to feature matrix if column schema requires clean numeric DataFrame
            X = df[
                [
                    "invoice_month",
                    "invoice_dayofweek",
                    "payment_terms_days",
                    "days_since_paperless",
                ]
            ]
            df["is_delayed"] = classifier.predict(X)
            if hasattr(classifier, "predict_proba"):
                df["risk_score"] = classifier.predict_proba(X)[:, 1]
            else:
                df["risk_score"] = df["is_delayed"].astype(float)

        # Filter Stage 1 Delayed Records (is_delayed == 1)
        delayed_df = df[df["is_delayed"] == 1].copy()

        # Format records for response
        records = []
        for idx, row in delayed_df.iterrows():
            billing_val = str(row.get("PaperlessBill", "")).strip().lower()
            billing_str = (
                "Paperless"
                if billing_val in ["1", "1.0", "yes", "true"]
                else "Standard"
            )

            records.append(
                {
                    "invoice_number": str(
                        row.get("invoiceNumber", f"790{idx}")
                    ),
                    "customer_id": str(row.get("customerID", "UNKNOWN")),
                    "amount": float(row.get("InvoiceAmount", 0.0)),
                    "billing_type": billing_str,
                    "risk_score": round(
                        float(row.get("risk_score", 0.95)) * 100, 1
                    ),
                    "due_date": str(row.get("DueDate", ""))[:10],
                }
            )

        total_val = (
            float(df["InvoiceAmount"].sum()) if "InvoiceAmount" in df else 0.0
        )
        at_risk_val = (
            float(delayed_df["InvoiceAmount"].sum())
            if "InvoiceAmount" in delayed_df
            else 0.0
        )

        return {
            "status": "success",
            "filename": file.filename,
            "metrics": {
                "total_invoices": len(df),
                "total_portfolio_val": total_val,
                "delayed_count": len(delayed_df),
                "at_risk_val": at_risk_val,
                "flagged_ratio": round(
                    (len(delayed_df) / len(df)) * 100 if len(df) > 0 else 0, 1
                ),
            },
            "records": records,
        }
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        raise HTTPException(
            status_code=400, detail=f"Failed to process file: {str(e)}"
        )


@app.post("/api/send-email")
def send_email(req: EmailRequest):
    sender = "sajesh.nair.ai@gmail.com"
    app_password = "ypqb bhys jkoq vcqg"  # Gmail App Password

    try:
        msg = MIMEText(req.body)
        msg["Subject"] = req.subject
        msg["From"] = sender
        msg["To"] = req.recipient

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.send_message(msg)

        return {
            "status": "success",
            "message": "Email dispatched successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))