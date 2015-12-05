# -*- coding: ascii -*-

"""
Bot library for euphoria.io.
"""

# ------------------------------------------------------------------------
# Preamble
# ------------------------------------------------------------------------

# Modules - Standard library
import sys, os, re, time
import json
import logging
import threading

# Modules - Additional. Must be installed.
import websocket
from websocket import WebSocketException as WSException, \
    WebSocketConnectionClosedException as WSCCException

# ------------------------------------------------------------------------
# Lowest abstraction layer.
# ------------------------------------------------------------------------

class JSONWebSocket:
    """
    JSONWebSocketWrapper(ws) -> new instance

    JSON-reading/writing WebSocket wrapper.
    Provides recv()/send() methods that transparently encode/decode JSON.
    """

    def __init__(self, ws):
        """
        __init__(ws) -> None

        Initializer. See class docstring for invocation details.
        """
        self.ws = ws
        self.lock = threading.RLock()

    def _recv_raw(self):
        """
        _recv_raw() -> str

        Receive a WebSocket frame, and return it unmodified.
        Raises a websocket.WebSocketConnectionClosedException (aliased to
        WSCCException in this module) if the underlying connection closed.
        """
        return self.ws.recv()

    def recv(self):
        """
        recv() -> object

        Receive a single WebSocket frame, decode it using JSON, and return
        the resulting object.
        Raises a websocket.WebSocketConnectionClosedException (aliased to
        WSCCException in this module) if the underlying connection closed.
        """
        return json.loads(self._recv_raw())

    def _send_raw(self, data):
        """
        _send_raw(data) -> None

        Send the given data without modification.
        Raises a websocket.WebSocketConnectionClosedException (aliased to
        WSCCException in this module) if the underlying connection closed.
        """
        self.ws.send(data)

    def send(self, obj):
        """
        send(obj) -> None

        JSON-encode the given object, and send it.
        Raises a websocket.WebSocketConnectionClosedException (aliased to
        WSCCException in this module) if the underlying connection closed.
        """
        self._send_raw(json.dumps(obj))

    def close(self):
        """
        close() -> None

        Close this connection. Repeated calls will succeed.
        """
        self.ws.close()
