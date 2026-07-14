from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/check")
def check_card(cc: str = Query(...)):
    parts = cc.split('|')
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="Invalid format")
    
    card_num, mm, yy, cvv_code = parts
    mm = mm.zfill(2)
    if len(yy) == 2:
        yy = '20' + yy

    try:
        # TEST 1: Cuba connect ke PayU terus tanpa buat order dulu
        # Kalau ini gagal, bermakna Railway block connection ke PayU
        test_payu = requests.get("https://secure.payu.com", timeout=10)
        
        return {
            "message": f"Railway boleh sambung ke PayU (Status: {test_payu.status_code}). Masalah ada di kod Create Order (fundacjakukuczki)."
        }

    except requests.exceptions.Timeout:
        return {"message": "ERROR: Railway timeout bila cuba sambung ke PayU. IP Railway diblok."}
    except Exception as e:
        return {"message": f"ERROR: Gagal sambung ke PayU. Sebab: {str(e)}"}
