try:
    import mdns_client
except ImportError:
    import mip
    mip.install("github:cbrand/micropython-mdns")
import network
import ujson
import os
import time
import hashlib
import urequests
import random
import uasyncio
from mdns_client import Client
from mdns_client.responder import Responder
import os

# Operational Config
WIFI_SSID = "SSID"
WIFI_PASS = "1234567890"

BEACON_URL = "https://beacon.openherd.dispherical.com"
BOOTSTRAPPING_PEERS = ["https://openherd.dispherical.com"]
PASSWORD = "SuperSecretRelayPW123!"
PUBLIC_KEY = "Me6vHCwTRja0fOGBQ6KQGoGCtUXeJ4dEKqUD1AfIoH4="
POSTS_DIR = "/.posts"
ENABLE_BEACON_DISCOVERY=False

# General things about your Openherd Relay
LAT = "33.7501"
LNG ="-84.3885"
NICKNAME = "My Club's Openherd Relay"
OPERATOR = "My Club"

PORT = 49152

if POSTS_DIR[1:] not in os.listdir('/'):
    os.mkdir(POSTS_DIR)

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    print("Connecting to WiFi...", end='')
    while not wlan.isconnected():
        print(".", end='')
        time.sleep(1)
    print("\nConnected:", wlan.ifconfig())
    return wlan.ifconfig()[0]

def read_posts(limit=None, offset=0):
    posts = []
    try:
        all_files = os.listdir(POSTS_DIR)
        files_to_process = all_files[offset:None if limit is None else offset+limit]
        for fname in files_to_process:
            try:
                with open(POSTS_DIR + "/" + fname) as f:
                    posts.append(ujson.load(f))
                import gc
                gc.collect()
            except:
                pass
    except:
        pass
    return posts

def save_post(post):
    post_id = post.get("id")
    if not post_id:
        post_id = hashlib.sha256(ujson.dumps(post).encode()).hexdigest()
    path = POSTS_DIR + "/" + post_id
    try:
        with open(path, "w") as f:
            ujson.dump(post, f)
    except:
        pass

def register(ip, ssid):
    if not ENABLE_BEACON_DISCOVERY:
        print("Beacon discovery disabled, skipping registration.")
        return
    msg = {
        "lat": LAT,
        "lng": LNG,
        "nickname": NICKNAME,
        "operator": OPERATOR,
        "ssid": ssid,
        "macAddress": network.WLAN(network.STA_IF).config('mac').hex(':')
    }
    payload = {
        "publicKey": PUBLIC_KEY,
        "message": ujson.dumps(msg),
        "password": PASSWORD
    }
    try:
        res = urequests.post(BEACON_URL + "/beacon/update", json=payload)
        print("Registered:", res.json())
    except Exception as e:
        print("Registration failed:", e)

# HTTP server
async def handle_client_async(reader, writer):
    addr = writer.get_extra_info('peername')
    try:
        request_line = await reader.readline()
        if not request_line:
            await writer.aclose()
            return

        request_line = request_line.decode().strip()
        print("Request:", request_line)
        method, path, _ = request_line.split()
        headers = {}
        while True:
            line = await reader.readline()
            if line == b"\r\n" or not line:
                break
            line = line.decode().strip()
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()

        content_length = int(headers.get("Content-Length", 0))
        body = await reader.read(content_length) if content_length else b""

        if method == "GET" and path == "/_openherd/outbox":
            limit = 10
            offset = 0
            
            if "?" in path:
                path, query = path.split("?", 1)
                params = query.split("&")
                for param in params:
                    if "=" in param:
                        key, value = param.split("=")
                        if key == "limit":
                            limit = int(value)
                        elif key == "offset":
                            offset = int(value)
            
            posts = read_posts(limit=limit, offset=offset)
            await writer.awrite(f"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
            await writer.awrite("[")
            
            for i, post in enumerate(posts):
                if i > 0:
                    await writer.awrite(",")
                post_json = ujson.dumps(post)
                await writer.awrite(post_json)
                await uasyncio.sleep_ms(10)
            await writer.awrite("]")
            import gc
            gc.collect()

        elif method == "POST" and path == "/_openherd/inbox":
            try:
                if len(body) != content_length:
                    response_json = ujson.dumps({"error": "Body length mismatch"})
                    response_bytes = response_json.encode('utf-8')
                    await writer.awrite(
                        f"HTTP/1.0 400 Bad Request\r\nContent-Type: application/json\r\nContent-Length: {len(response_bytes)}\r\n\r\n"
                    )
                    await writer.awrite(response_bytes)
                    import gc
                    gc.collect()
                    return

                import gc
                gc.collect()

                body_str = body.decode('utf-8')
                posts = ujson.loads(body_str)

                if not isinstance(posts, list):
                    raise ValueError("Expected JSON array")

                for post in posts:
                    try:
                        import gc
                        gc.collect()
                        save_post(post)
                    except Exception as e:
                        print(f"Error processing item: {e}")

                response_json = ujson.dumps({"ok": True})

            except ValueError as ve:
                import gc
                gc.collect()
                print(f"JSON parsing error: {ve}")
                response_json = ujson.dumps({"error": "Invalid JSON format"})

            except Exception as e:
                print(f"General error: {e}")
                response_json = ujson.dumps({"error": str(e)})

            response_bytes = response_json.encode('utf-8')
            content_length = len(response_bytes)
            await writer.awrite(
                f"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: {content_length}\r\n\r\n"
            )
            await writer.awrite(response_bytes)
        else:
            not_found_message = f"   ____                   _                  _ \n  / __ \\                 | |                | |\n | |  | |_ __   ___ _ __ | |__   ___ _ __ __| |\n | |  | | '_ \\ / _ \\ '_ \\| '_ \\ / _ \\ '__/ _` |\n | |__| | |_) |  __/ | | | | | |  __/ | | (_| |\n  \\____/| .__/ \\___|_| |_|_| |_|\\___|_|  \\__,_|\n        | |                                    \n        |_|\n\nOpenHerd is a way for people to chat and share short, temporary messages without anyone really knowing who they are.\nThink of it as a digital bulletin board for a local area, but super private.\nIt's built using Free and Open Source Software (FOSS), meaning it's created by a community and anyone can see how it works.\nIt's also peer-to-peer, which means messages go directly between people's devices rather than through a central company.\n\nLearn more at https://github.com/openherd\n\nDevice: {os.uname().machine}\nNickname: {NICKNAME}\nOperator: {OPERATOR}"
            await writer.awrite(f"HTTP/1.0 200 OK\r\nContent-Length: {len(not_found_message)}\r\nContent-Type: text/plain\r\n\r\n")
            await writer.awrite(not_found_message)
    finally:
        await writer.aclose()
        import gc
        gc.collect()

async def start_http_server(port):
    server = await uasyncio.start_server(handle_client_async, "0.0.0.0", port)
    print("HTTP server running on port", port)
    return server

# Syncing (As defined in section 6)
async def sync_loop():
    BATCH_SIZE = 1
    
    while True:
        for peer in BOOTSTRAPPING_PEERS:
            try:
                print(f"Syncing with {peer}/_openherd/inbox")
                
                all_posts = os.listdir(POSTS_DIR)
                for i in range(0, len(all_posts), BATCH_SIZE):
                    batch = []
                    for j in range(i, min(i + BATCH_SIZE, len(all_posts))):
                        try:
                            with open(POSTS_DIR + "/" + all_posts[j]) as f:
                                batch.append(ujson.load(f))
                        except:
                            pass
                    
                    if batch:
                        urequests.post(peer + "/_openherd/inbox", json=batch)
                        await uasyncio.sleep(1)
                
                print(f"Fetching from {peer}/_openherd/outbox")
                res = urequests.get(peer + "/_openherd/outbox")
                posts = res.json()
                for i in range(0, len(posts), BATCH_SIZE):
                    for j in range(i, min(i + BATCH_SIZE, len(posts))):
                        save_post(posts[j])
                    await uasyncio.sleep(1)

                print(f"Sync with {peer} successful.")
            except Exception as e:
                print(f"Sync failed with {peer}:", e)
                
        await uasyncio.sleep(300)

# mDNS advertisement (cbrand/micropython-mdns)
async def start_mdns(ip, port):
    client = Client(ip)
    responder = Responder(client, own_ip=lambda: ip, host=lambda: f"openherd-{random.randint(1000,9999)}")
    responder.advertise(
        "_openherd", "_tcp", port=port,
        data={"device": os.uname().machine},
        service_host_name=f"openherd relay ({random.randint(1000,9999)})"
    )
    print("mDNS advertisement started")

# Main Function
async def main():
    ip = connect_wifi(WIFI_SSID, WIFI_PASS)
    port = PORT
    register(ip, WIFI_SSID)

    await start_mdns(ip, port)
   
    uasyncio.create_task(start_http_server(port))
    uasyncio.create_task(sync_loop())

    while True:
        await uasyncio.sleep(3600) # Keep the main loop alive


uasyncio.run(main())