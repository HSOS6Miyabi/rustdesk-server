"""Integration test of WebRTC signaling through a running hbbs service."""

import base64
import os
import socket
import struct


def varint(value):
    output = bytearray()
    while value >= 128:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def raw_field(field, value):
    return varint(field * 8 + 2) + varint(len(value)) + value


def text_field(field, value):
    return raw_field(field, value.encode("utf-8"))


def integer_field(field, value):
    return varint(field * 8) + varint(value)


def parse_fields(data):
    parsed = {}
    pos = 0
    while pos < len(data):
        key, pos = parse_varint(data, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = parse_varint(data, pos)
        elif wire == 2:
            length, pos = parse_varint(data, pos)
            if length > len(data) - pos:
                raise AssertionError("Truncated protobuf message")
            value = data[pos:pos + length]
            pos += length
        else:
            raise AssertionError(f"Unexpected protobuf wire type {wire}")
        parsed.setdefault(field, []).append(value)
    return parsed


def parse_varint(data, pos):
    value, shift = 0, 0
    while pos < len(data) and shift < 70:
        b = data[pos]
        pos += 1
        value |= (b & 127) << shift
        if not b & 128:
            return value, pos
        shift += 7
    raise AssertionError("Invalid protobuf integer")


def recv_exact(sock, size):
    result = bytearray()
    while len(result) < size:
        block = sock.recv(size - len(result))
        if not block:
            raise EOFError("Connection closed while reading signaling message")
        result.extend(block)
    return bytes(result)


def send_framed(sock, payload):
    length = len(payload)
    if length <= 63:
        prefix = bytes([length << 2])
    elif length <= 16383:
        prefix = struct.pack("<H", (length << 2) | 1)
    else:
        prefix = struct.pack("<I", (length << 2) | 3)
    sock.sendall(prefix + payload)


def ws_upgrade(port):
    sock = socket.create_connection(("127.0.0.1", port), timeout=6)
    sock.settimeout(6)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        "GET / HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Connection: Upgrade\r\n"
        "Upgrade: websocket\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode("ascii")
    sock.sendall(request)
    header = bytearray()
    while b"\r\n\r\n" not in header:
        header.extend(sock.recv(1))
        if len(header) > 8192:
            raise AssertionError("Oversized WebSocket response")
    if b"101 Switching Protocols" not in header:
        raise AssertionError(f"WebSocket upgrade failed: {header[:150]!r}")
    return sock


def ws_send_binary(sock, value):
    mask = os.urandom(4)
    length = len(value)
    if length < 126:
        header = bytes([0x82, 0x80 | length])
    elif length <= 65535:
        header = bytes([0x82, 0xFE]) + struct.pack("!H", length)
    else:
        raise AssertionError("Unexpected oversized test message")
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(value))
    sock.sendall(header + mask + masked)


def ws_recv_binary(sock):
    first, second = recv_exact(sock, 2)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", recv_exact(sock, 8))[0]
    if length > 65536:
        raise AssertionError("Oversized WebSocket reply")
    mask = recv_exact(sock, 4) if second & 0x80 else None
    data = recv_exact(sock, length)
    if mask:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    if first & 0x0F != 2:
        raise AssertionError(f"Unexpected WebSocket opcode {first & 0x0F}")
    return data


def check_webrtc_signaling(base):
    """Verify real hbbs registration, SDP forwarding and browser ICE delivery."""
    target = "webrtc-signal-target"
    offer = "webrtc://test-offer-value"
    answer = "webrtc://test-answer-value"
    session_key = "sha-256 FF:EE:DD"

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(6)
        register = text_field(1, target)
        receiver.sendto(raw_field(6, register), ("127.0.0.1", base))
        reply, _ = receiver.recvfrom(4096)
        if 7 not in parse_fields(reply):
            raise AssertionError("Device registration did not receive a server reply")

        register_pk = (
            text_field(1, target) +
            raw_field(2, os.urandom(16)) +
            raw_field(3, os.urandom(32))
        )
        receiver.sendto(raw_field(15, register_pk), ("127.0.0.1", base))
        reply, _ = receiver.recvfrom(4096)
        if 16 not in parse_fields(reply):
            raise AssertionError("Device public key registration failed")

        with ws_upgrade(base + 2) as caller:
            # WebSocket requests avoid same-LAN address retrieval and exercise
            # the exact transport used by the browser WebClient.
            punch = (
                text_field(1, target) +
                integer_field(2, 2) +
                text_field(12, offer)
            )
            ws_send_binary(caller, raw_field(8, punch))

            message, _ = receiver.recvfrom(65536)
            outer = parse_fields(message)
            if 9 not in outer:
                raise AssertionError("Registered device did not receive PunchHole")
            forwarded = parse_fields(outer[9][0])
            if forwarded.get(10, [None])[0] != offer.encode():
                raise AssertionError("WebRTC SDP offer was not preserved")
            return_addr = forwarded.get(1, [None])[0]
            if not return_addr:
                raise AssertionError("PunchHole did not include a return address")

            # The controlled device reports its SDP answer on the RustDesk
            # TCP signaling port, preserving the return address exactly.
            with socket.create_connection(("127.0.0.1", base), timeout=6) as response:
                response.settimeout(6)
                sent = (
                    raw_field(1, return_addr) +
                    text_field(2, target) +
                    text_field(5, "1.5.1") +
                    text_field(8, answer)
                )
                send_framed(response, raw_field(10, sent))

            reply = parse_fields(ws_recv_binary(caller))
            if 11 not in reply:
                raise AssertionError("Browser did not receive PunchHoleResponse")
            reported = parse_fields(reply[11][0])
            if reported.get(12, [None])[0] != answer.encode():
                raise AssertionError("WebRTC SDP answer was not preserved")

            candidate = (
                text_field(1, target) +
                text_field(3, session_key) +
                text_field(4, '{"candidate":"candidate:1 1 udp 1 192.0.2.3 1000 typ host"}')
            )
            ws_send_binary(caller, raw_field(29, candidate))
            message, _ = receiver.recvfrom(65536)
            outer = parse_fields(message)
            if 29 not in outer:
                raise AssertionError("Registered device did not receive WebRTC ICE candidate")
            forwarded_ice = parse_fields(outer[29][0])
            if forwarded_ice.get(3, [None])[0] != session_key.encode():
                raise AssertionError("ICE candidate session key was not preserved")

    print("WebRTC SDP offer, SDP answer and ICE candidate forwarding passed.")
