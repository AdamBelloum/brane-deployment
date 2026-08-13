#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

secret_path = Path(sys.argv[1])
secret = json.loads(secret_path.read_text())
key_obj = secret["keys"][0]

key_b64 = key_obj["k"]
key = base64.urlsafe_b64decode(key_b64 + "=" * (-len(key_b64) % 4))

now = int(time.time())

header = base64.urlsafe_b64encode(
    json.dumps(
        {"alg": "HS256", "typ": "JWT", "kid": key_obj["kid"]},
        separators=(",", ":"),
    ).encode()
).rstrip(b"=").decode()

payload = base64.urlsafe_b64encode(
    json.dumps(
        {
            "sub": "brane-job",
            "username": "brane-job",
            "iat": now,
            "exp": now + 315360000,
        },
        separators=(",", ":"),
    ).encode()
).rstrip(b"=").decode()

message = f"{header}.{payload}".encode()
signature = base64.urlsafe_b64encode(
    hmac.new(key, message, hashlib.sha256).digest()
).rstrip(b"=").decode()

print(f"{header}.{payload}.{signature}")
