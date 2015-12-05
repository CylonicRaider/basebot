# -*- coding: ascii -*-

"""
Bot library for euphoria.io.
"""

# ---------------------------------------------------------------------------
# Preamble
# ---------------------------------------------------------------------------

# Version.
__version__ = "2.0"

# Modules - Standard library
import sys, os, re, time
import json
import logging
import threading

# Modules - Additional. Must be installed.
import websocket
from websocket import WebSocketException as WSException, \
    WebSocketConnectionClosedException as WSCCException

# ---------------------------------------------------------------------------
# Lowest abstraction layer.
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Record classes.
# ---------------------------------------------------------------------------

class Record(dict):
    """
    Record(...) -> dict

    A dictionary that exports some items as attributes; as well as provides
    static defaults for some keys.
    """

    # Export list.
    _exports_ = ()

    # Defaults mapping.
    _defaults_ = {}

    def __getattr__(self, name):
        if name not in self._exports_:
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name not in self._exports_:
            raise AttributeError(name)
        try:
            self[name] = value
        except KeyError:
            raise AttributeError(name)

    def __delattr__(self, name):
        if name not in self._exports_:
            raise AttributeError(name)
        try:
            del self[name]
        except KeyError:
            raise AttributeError(name)

    def __missing__(self, key):
        return self._defaults_[key]

# Constructed after github.com/euphoria-io/heim/blob/master/doc/api.md as of
# commit 03906c0594c6c7ab5e15d1d8aa5643c847434c97.

class Packet(Record):
    """
    The "basic" members any packet must/may have.

    Attributes:
    id              :  client-generated id for associating replies with
                       commands (optional)
    type            :  the name of the command, reply, or event
    data            :  the payload of the command, reply, or event (optional)
    error           :  this field appears in replies if a command fails
                       (optional)
    throttled       :  this field appears in replies to warn the client that
                       it may be flooding; the client should slow down its
                       command rate (defaults to False)
    throttled_reason:  if throttled is true, this field describes why
                       (optional)
    """
    _exports_ = ('id', 'type', 'data', 'error', 'throttled',
                 'throttled_reason')

class AccountView(Record):
    """
    AccountView describes an account and its preferred names.

    Attributes:
    id  : the id of the account
    name: the name that the holder of the account goes by
    """
    _exports_ = ('id', 'name')

class Message(Record):
    """
    A Message is a node in a Room's Log. It corresponds to a chat message, or
    a post, or any broadcasted event in a room that should appear in the log.

    Attributes:
    id               : the id of the message (unique within a room)
    parent           : the id of the message's parent, or null if top-level
                       (optional)
    previous_edit_id : the edit id of the most recent edit of this message,
                       or None if it's never been edited (optional)
    time             : the unix timestamp of when the message was posted
    sender           : the view of the sender's session (SessionView)
    content          : the content of the message (client-defined)
    encryption_key_id: the id of the key that encrypts the message in storage
                       (optional)
    edited           : the unix timestamp of when the message was last edited
                       (optional)
    deleted          : the unix timestamp of when the message was deleted
                       (optional)
    truncated        : if true, then the full content of this message is not
                       included (see get-message to obtain the message with
                       full content) (optional)

    All optional attributes default to None.
    """
    _exports_ = ('id', 'parent', 'previous_edit_id', 'time', 'sender',
                 'content', 'encryption_key_id', 'edited', 'deleted',
                 'truncated')

    _defaults_ = {'parent': None, 'previous_edit_id': None,
                  'encryption_key_id': None, 'edited': None, 'deleted': None,
                  'truncated': None}

class SessionView(Record):
    """
    SessionView describes a session and its identity.

    Attributes:
    id        : the id of an agent or account
    name      : the name-in-use at the time this view was captured
    server_id : the id of the server that captured this view
    server_era: the era of the server that captured this view
    session_id: id of the session, unique across all sessions globally
    is_staff  : if true, this session belongs to a member of staff (defaults
                to False)
    is_manager: if true, this session belongs to a manager of the room
                (defaults to False)
    """
    _exports_ = ('id', 'name', 'server_id', 'server_era', 'session_id',
                 'is_staff', 'is_manager')

    _defaults_ = {'is_staff': False, 'is_manager': False}
