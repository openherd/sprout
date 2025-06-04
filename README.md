# 🌱 sprout — a MicroPython OpenHerd Relay

Sprout is a lightweight HTTP relay that runs on a Raspberry Pi Pico W or ESP32. It syncs OpenHerd messages, stores them offline, advertises itself over mDNS, and can optionally register with a global beacon for discovery. It is a work-in-progress implementation of the full relay spec.

## Quick Start

1. Flash your board with [This fork of MicroPython](https://github.com/cbrand/micropython-mdns/releases) (select the uf2 file, `firmware.mp.<version>.rp2.uf2`)
2. Set your WiFi/network in `main.py`.
3. Run it with:

```bash
mpremote cp main.py :main.py
mpremote run main.py
```

You can see if it's running by trying to query your network for openherd nodes:
```bash
avahi-browse -r _openherd._tcp
```

## Creating a beacon entry (optional)
To list your beacon on the map, you'll need to generate a key and set a password.
1. Clone `https://github.com/openherd/relay` to your computer
2. `yarn install` the modules.
3. Generate a pubkey/privkey pair using `node cli/keygen`
4. Set the password using `node cli/password`. It will prompt you for the password
5. Get the key from `./.data/.publickey` (`cat ./.data/.publickey`) and set it to the `PUBLIC_KEY` variable in main.py. Set the password you chose to the `PASSWORD` variable as well.

```python
PASSWORD = "SuperSecretRelayPW123!"
PUBLIC_KEY = "Me6vHCwTRja0fOGBQ6KQGoGCtUXeJ4dEKqUD1AfIoH4="
ENABLE_BEACON_DISCOVERY=True # Set this to true as well
```