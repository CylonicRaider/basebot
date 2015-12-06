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

# Regex for @-mentions
# From github.com/euphoria-io/heim/blob/master/client/lib/stores/chat.js as
# of commit f9d5527beb41ac3e6e0fee0c1f5f4745c49d8f7b (adapted).
_MENTION_DELIMITER = r'[,.!?;&<\'"\s]'
MENTION_RE = re.compile('(?:^|(?<=' + _MENTION_DELIMITER + r'))@(\S+?)(?=' +
                        _MENTION_DELIMITER + '|$)')

# Regex for whitespace.
WHITESPACE_RE = re.compile('\s+')

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def normalize_nick(nick):
    """
    normalize_nick(nick) -> str

    Remove whitespace from the given nick, and perform any other
    normalizations on it.
    """
    return WHITESPACE_RE.sub('', nick).lower()

def format_datetime(timestamp, fractions=True):
    """
    format_datetime(timestamp, fractions=True) -> str

    Produces a string representation of the timestamp similar to
    the ISO 8601 format: "YYYY-MM-DD HH:MM:SS.FFF UTC". If fractions
    is false, the ".FFF" part is omitted. As the platform the bots
    are used on is international, there is little point to use any kind
    of timezone but UTC.

    See also: format_delta()
    """
    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamp))
    if fractions: ts += '.%03d' % (int(timestamp * 1000) % 1000)
    return ts + ' UTC'

def format_delta(delta, fractions=True):
    """
    format_delta(delta, fractions=True) -> str

    Format a time difference. delta is a numeric value holding the time
    difference to be formatted in seconds. The return value is composed
    like that: "[- ][Xd ][Xh ][Xm ][X[.FFF]s]", with the brackets indicating
    possible omission. If fractions is False, or the given time is an
    integer, the fractional part is omitted. All components are included as
    needed, so the result for 3600 would be "1h". As a special case, the
    result for 0 is "0s" (instead of nothing).

    See also: format_datetime()
    """
    if not fractions:
        delta = int(delta)
    if delta == 0: return '0s'
    ret = []
    if delta < 0:
        ret.append('-')
        delta = -delta
    if delta >= 86400:
        ret.append('%dd' % (delta // 86400))
        delta %= 86400
    if delta >= 3600:
        ret.append('%dh' % (delta // 3600))
        delta %= 3600
    if delta >= 60:
        ret.append('%dm' % (delta // 60))
        delta %= 60
    if delta != 0:
        if delta % 1 != 0:
            ret.append('%ss' % round(delta, 3))
        else:
            ret.append('%ds' % delta)
    return ' '.join(ret)

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

    A dictionary that exports some items as attributes as well as provides
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

    Additional read-only properties:
    mention_list: Tuple of (offset, string) pairs listing all the @-mentions
                  in the message (including the @ signs).
    mention_set : frozenset of names @-mentioned in the message (excluding
                  the @ signs).
    """
    _exports_ = ('id', 'parent', 'previous_edit_id', 'time', 'sender',
                 'content', 'encryption_key_id', 'edited', 'deleted',
                 'truncated')

    _defaults_ = {'parent': None, 'previous_edit_id': None,
                  'encryption_key_id': None, 'edited': None, 'deleted': None,
                  'truncated': None}

    def __init__(__self, *__args, **__kwds):
        Record.__init__(__self, *__args, **__kwds)
        __self.__lock = threading.RLock()
        __self.__mention_list = None
        __self.__mention_set = None

    def __setitem__(self, key, value):
        with self.__lock:
            Record.__setitem__(self, key, value)
            self.__mention_list = None
            self.__mention_set = None

    @property
    def mention_list(self):
        with self.__lock:
            if self.__mention_list is None:
                l, s, o = [], self.content, 0
                ls = len(s)
                while o < ls:
                    m = MENTION_RE.search(s, o)
                    if not m: break
                    l.append((m.start(), m.group()))
                    o = m.end()
                self.__mention_list = tuple(l)
            return self.__mention_list

    @property
    def mention_set(self):
        with self.__lock:
            if self.__mention_set is None:
                self.__mention_set = frozenset(i[1][1:]
                    for i in self.__mention_list)
            return self.__mention_set

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

    Additional read-only properties:
    is_account: Whether this session has an account.
    is_agent  : Whether this session is neither a bot nor has an account.
    is_bot    : Whether this is a bot.
    norm_name : Normalized name.
    """
    _exports_ = ('id', 'name', 'server_id', 'server_era', 'session_id',
                 'is_staff', 'is_manager')

    _defaults_ = {'is_staff': False, 'is_manager': False}

    @property
    def is_account(self):
        return self['id'].startswith('account:')

    @property
    def is_agent(self):
        return self['id'].startswith('agent:')

    @property
    def is_bot(self):
        return self['id'].startswith('bot:')

    @property
    def norm_name(self):
        return normalize_nick(self.name)
