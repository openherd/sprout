try:
    import mdns_client
except ImportError:
    import mip
    mip.install("github:cbrand/micropython-mdns")
import network
import socket
import ujson
import os
import time
import hashlib
import urequests
import random
import uasyncio
from mdns_client import Client
from mdns_client.responder import Responder

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

def find_free_port(start_port=49152, end_port=65535, max_attempts=100):
    for _ in range(max_attempts):
        port = random.randint(start_port, end_port)
        try:
            s = socket.socket()
            s.bind(('', port))
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError("Could not find free port")

def read_posts():
    posts = []
    try:
        for fname in os.listdir(POSTS_DIR):
            try:
                with open(POSTS_DIR + "/" + fname) as f:
                    posts.append(ujson.load(f))
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
            posts = read_posts()
            response_json = ujson.dumps(posts)
            response_bytes = response_json.encode('utf-8')
            await writer.awrite(f"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(response_bytes)}\r\n\r\n")
            await writer.awrite(response_bytes)

        elif method == "POST" and path == "/_openherd/inbox":
            try:
                posts = ujson.loads(body)
                if not isinstance(posts, list):
                    raise ValueError("Expected list")
                for post in posts:
                    save_post(post)
                response_json = ujson.dumps({"ok":True})
                response_bytes = response_json.encode('utf-8')
                await writer.awrite(f"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(response_bytes)}\r\n\r\n")
                await writer.awrite(response_bytes)
            except Exception as e:
                error_message_bytes = str(e).encode('utf-8')
                await writer.awrite(f"HTTP/1.0 400 Bad Request\r\nContent-Length: {len(error_message_bytes)}\r\n\r\n")
                await writer.awrite(error_message_bytes)
        else:
            not_found_message = b"404 Not Found"
            await writer.awrite(f"HTTP/1.0 404 Not Found\r\nContent-Length: {len(not_found_message)}\r\n\r\n")
            await writer.awrite(not_found_message)
    finally:
        await writer.aclose()

async def start_http_server(port):
    server = await uasyncio.start_server(handle_client_async, "0.0.0.0", port)
    print("HTTP server running on port", port)
    return server

# Syncing (As defined in section 6)
async def sync_loop():
    while True:
        posts = read_posts()
        for peer in BOOTSTRAPPING_PEERS:
            try:
                print(f"Syncing with {peer}/_openherd/inbox")
                urequests.post(peer + "/_openherd/inbox", json=posts)
                print(f"Fetching from {peer}/_openherd/outbox")
                res = urequests.get(peer + "/_openherd/outbox")
                for post in res.json():
                    save_post(post)
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
        data={"device": "picow"},
        service_host_name=f"openherd relay ({random.randint(1000,9999)})"
    )
    print("mDNS advertisement started")

# Main Function
async def main():
    ip = connect_wifi(WIFI_SSID, WIFI_PASS)
    port = find_free_port()
    register(ip, WIFI_SSID)

    await start_mdns(ip, port)
   
    uasyncio.create_task(start_http_server(port))
    uasyncio.create_task(sync_loop())

    while True:
        await uasyncio.sleep(3600) # Keep the main loop alive


uasyncio.run(main())