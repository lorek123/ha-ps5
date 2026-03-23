"""Test DDP WAKEUP using credential from regist_ps5.py registration."""

import asyncio
import sys

sys.path.insert(0, "src")
from psn_ddp import async_get_status, async_wakeup

PS5_IP = "192.168.1.190"

# From regist_ps5.py output:
# PS5-RegistKey: 6131623066343762
# Decoded: a1b0f47b → uint64_t = 2712728699
REGIST_KEY_RAW = "6131623066343762"
regist_key_bytes = bytes.fromhex(REGIST_KEY_RAW).rstrip(b"\x00")
credential_int = int(regist_key_bytes.decode("ascii"), 16)
credential_str = str(credential_int)
print(f"DDP user-credential (decimal): {credential_str}")


async def main():
    status = await async_get_status(PS5_IP)
    print(f"Status before wake: {status}")
    if status and status.status == 620:
        print("Sending WAKEUP...")
        await async_wakeup(PS5_IP, credential=credential_str)
        print("Sent. Polling...")
        for _ in range(12):
            await asyncio.sleep(5)
            s = await async_get_status(PS5_IP)
            print(f"  status: {s}")
            if s and s.status == 200:
                print("PS5 is ON!")
                break
    elif status and status.status == 200:
        print("PS5 is already ON")
    else:
        print("PS5 not found")


asyncio.run(main())
