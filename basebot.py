# -*- coding: ascii -*-

"""
Bot library for euphoria.io.

Important functions and classes:
normalize_nick() : Normalize a nick (remove whitespace and convert it to
                   lower case). Useful for comparison of @-mentions.
format_datetime(): Format a UNIX timestamp nicely.
format_delta()   : Format a timestamp difference nicely.

Packet           : An Euphorian packet.
Message          : Representing a single message.
SessionView      : Representing a single session.

HeimEndpoint     : A bare-bones implementation of the API; useful for
                   minimalistic clients, or alternative expansion.
LoggingEndpoint  : HeimEndpoint maintaining a user list and chat logs
                   on demand.
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

# Default connection URL template.
URL_TEMPLATE = os.environ.get('BASEBOT_URL_TEMPLATE',
                              'wss://euphoria.io/room/{}/ws')

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

    Produces a string representation of the timestamp similar to the
    ISO 8601 format: "YYYY-MM-DD HH:MM:SS.FFF UTC". If fractions is false,
    the ".FFF" part is omitted. As the platform the bots are used on is
    international, there is little point to use any kind of timezone but
    UTC.
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

class Record(dict):
    """
    Record(...) -> new instance

    A dictionary that exports some items as attributes as well as provides
    static defaults for some keys. Can be constructed in any way a dict
    can.
    """

    # Export list.
    _exports_ = ()

    # Defaults mapping.
    _defaults_ = {}

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, dict.__repr__(self))

    def __getattr__(self, name):
        if name not in self._exports_:
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            return dict.__setattr__(self, name, value)
        elif name not in self._exports_:
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

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BasebotException(Exception):
    "Base exception class."

class NoRoomError(BasebotException):
    "No room specified before HeimEndpoint.connect() call."

class NoConnectionError(BasebotException):
    "HeimEndpoint currently connected."

# ---------------------------------------------------------------------------
# Lowest abstraction layer.
# ---------------------------------------------------------------------------

class JSONWebSocket:
    """
    JSONWebSocketWrapper(ws) -> new instance

    JSON-reading/writing WebSocket wrapper.
    Provides recv()/send() methods that transparently encode/decode JSON.
    Reads and writes are serialized with independent locks; the reading
    lock is to be acquired "outside" the write lock.
    """

    def __init__(self, ws):
        """
        __init__(ws) -> None

        Initializer. See class docstring for invocation details.
        """
        self.ws = ws
        self.rlock = threading.RLock()
        self.wlock = threading.RLock()

    def _recv_raw(self):
        """
        _recv_raw() -> str

        Receive a WebSocket frame, and return it unmodified.
        Raises a websocket.WebSocketConnectionClosedException (aliased to
        WSCCException in this module) if the underlying connection closed.
        """
        with self.rlock:
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
        with self.wlock:
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

        Close this connection. Repeated calls will succeed immediately.
        """
        self.ws.close()

# ---------------------------------------------------------------------------
# Euphorian protocol.
# ---------------------------------------------------------------------------

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

## Currently unused.
#class AccountView(Record):
#    """
#    AccountView describes an account and its preferred names.
#
#    Attributes:
#    id  : the id of the account
#    name: the name that the holder of the account goes by
#    """
#    _exports_ = ('id', 'name')

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

class UserList(object):
    """
    UserList() -> new instance

    An iterable list of SessionView objects, with methods for modification
    and quick search.
    """

    def __init__(self):
        """
        __init__() -> None

        Constructor. See class docstring for usage.
        """
        self._list = []
        self._by_session_id = {}
        self._by_agent_id = {}
        self._by_name = {}
        self._lock = threading.RLock()

    def __iter__(self):
        """
        __iter__() -> iterator

        Iterate over all elements in self.
        """
        return iter(self.list())

    def add(self, *lst):
        """
        add(*lst) -> None

        Add all the SessionView-s in lst to self, unless already there.
        """
        with self._lock:
            for i in lst:
                if i.session_id in self._by_session_id:
                    orig = self._by_session_id.pop(i.session_id)
                    self._list.remove(orig)
                    self._by_agent_id[orig.id].remove(orig)
                    self._by_name[orig.name].remove(orig)
                self._list.append(i)
                self._by_session_id[i.session_id] = i
                self._by_agent_id.setdefault(i.id, []).append(i)
                self._by_name.setdefault(i.name, []).append(i)

    def remove(self, *lst):
        """
        remove(*lst) -> None

        Remove all the SessionView-s in lst from self (unless not there
        at all).
        """
        with self._lock:
            for i in lst:
                try:
                    orig = self._by_session_id.pop(i.session_id)
                except KeyError:
                    continue
                self._list.remove(orig)
                self._by_agent_id.get(orig.id, []).remove(orig)
                self._by_name.get(orig.name, []).remove(orig)

    def remove_matching(self, pattern):
        """
        remove_matching(pattern) -> None

        Remove all the SessionView-s from self where all the items present
        in pattern equal to the corresponding ones in the element; i.e.,
        a pattern of {'name': 'test'} will remove all entries with a 'name'
        value of 'test'. An empty pattern will remove all users.
        Used to implement the partition network-event.
        """
        with self._lock:
            if not pattern:
                self.clear()
                return
            rml, it = [], pattern.items()
            for i in self._list:
                for k, v in it:
                    try:
                        if i[k] != v:
                            break
                    except KeyError:
                        break
                else:
                    rml.append(i)
            self.remove(*rml)

    def clear(self):
        """
        clear() -> None

        Remove everything from self.
        """
        with self._lock:
            self._list[:] = ()
            self._by_session_id.clear()
            self._by_agent_id.clear()
            self._by_name.clear()

    def list(self):
        """
        list() -> list

        Return a (Python) list holding all the SessionViews currently in
        here.
        """
        with self._lock:
            return list(self._list)

    def for_session(self, id):
        """
        for_session(id) -> SessionView

        Return the SessionView corresponding session ID from self.
        Raises a KeyError if the given session is not known.
        """
        with self._lock:
            return self._by_session_id[id]

    def for_agent(self, id):
        """
        for_agent(id) -> list

        Return all the SessionViews known with the given agent ID as a list.
        """
        with self._lock:
            return list(self._by_agent_id.get(id, ()))

    def for_name(self, name):
        """
        for_name(name) -> list

        Return all the SessionViews known with the given name as a list.
        """
        with self._lock:
            return list(self._by_name.get(name, ()))

class MessageTree(object):
    """
    MessageTree() -> new instance

    Class representing a threaded chat log. Note that, because of Heim's
    never-forget policy, "deleted" messages are actually only flagged as
    such, and not "physically" deleted. Editing messages happens by
    re-adding them.
    """

    def __init__(self):
        """
        __init__() -> None

        Constructor. See class docstring for usage.
        """
        self._messages = {}
        self._children = {}
        self._earliest = None
        self._latest = None
        self._lock = threading.RLock()

    def __iter__(self):
        """
        __iter__() -> iterator

        Iterate over all elements in self in order.
        """
        return iter(self.list())

    def __getitem__(self, key):
        """
        __getitem__(key) -> Message

        Equivalent to self.get(key).
        """
        return self.get(key)

    def add(self, *lst):
        """
        add(*lst) -> None

        Incorporate all the messages in lst into self.
        """
        sorts = set()
        with self._lock:
            for msg in lst:
                self._messages[msg.id] = msg
                c = self._children.setdefault(msg.parent, [])
                if msg.id not in c: c.append(msg.id)
                if self._earliest is None or self._earliest.id > msg.id:
                    self._earliest = msg
                if self._latest is None or self._latest.id <= msg.id:
                    self._latest = msg
                sorts.add(c)
            for l in sorts:
                l.sort(key=lambda m: m.id)

    def clear(self):
        """
        clear() -> None

        (Actually) remove all the messages from self.
        """
        with self._lock:
            self._messages.clear()
            self._children.clear()
            self._earliest = None
            self._latest = None

    def earliest(self):
        """
        earliest() -> Message

        Return the earliest message in self, or None of none.
        """
        with self._lock:
            return self._earliest

    def latest(self):
        """
        latest() -> Message

        Return the latest message in self, or None of none.
        """
        with self._lock:
            return self._latest

    def get(self, id):
        """
        get(id) -> Message

        Return the message corresponding to the given ID, or raise KeyError
        if no such message present.
        """
        with self._lock:
            return self._messages[id]

    def list(self, parent=None):
        """
        list(parent=None) -> list

        Return all the messages for the given parent (None for top-level
        messages) in an ordered list.
        """
        with self._lock:
            return [self._messages[i]
                    for i in self._children.get(parent, ())]

    def all(self):
        """
        all() -> list

        Return an ordered list containing all the messages in self.
        """
        with self._lock:
            l = list(self._messages.values())
            l.sort(key=lambda m: m.id)
            return l

class HeimEndpoint(object):
    """
    HeimEndpoint(**config) -> new instance

    Endpoint for the Heim protocol. Provides state about this endpoint and
    the connection, methods to submit commands, as well as call-back methods
    for some incoming replies/events, and dynamic handlers for arbitrary
    incoming packets. Re-connects are handled transparently.

    Attributes (assignable by keyword arguments):
    url_template: Template to construct URLs from. Its format() method
                  will be called with the room name as the only argument.
                  Defaults to the global URL_TEMPLATE variable, which, in
                  turn, may be overridden by the environment variable
                  BASEBOT_URL_TEMPLATE (if set when the module is
                  initialized).
    roomname    : Name of room to connect to. Defaults to None. Must be
                  explicitly set for the connection to succeed.
    nickname    : Nick-name to set on connection. Updated when a nick-reply
                  is received. Defaults to None; in that case, no nick-name
                  is set.
    passcode    : Passcode for private rooms. Sent during (re-)connection.
                  Defaults to None; no passcode is sent in that case.
    retry_count : Amount of re-connection attempts until an operation (a
                  connect or a send) fails.
    retry_delay : Amount of seconds to wait before a re-connection attempt.
    handlers    : Packet-type-to-list-of-callables mapping storing handlers
                  for incoming packets.
                  Handlers are called with the packet as the only argument;
                  the packet's '_self' item is set to the HeimEndpoint
                  instance that received the packet.
                  Handlers for the (virtual) packet type None (i.e. the None
                  singleton) are called for *any* packet, similarly to
                  handle_any() (but *after* the built-in handlers).
                  While commands and replies should be handled by the
                  call-back mechanism, built-in handler methods (on_*();
                  not in the mapping) are present for the asynchronous
                  events.
                  Event handlers are (indirectly) called from the input loop,
                  and should therefore finish quickly, or offload the work
                  to a separate thread. Mind that the Heim server will kick
                  any clients unreponsive for too long times!
                  While account-related event handlers are present, actual
                  support for accounts is lacking, and has to be implemented
                  manually.

    Access to the attributes should be serialized using the instance lock
    (available in the lock attribute). The __enter__ and __exit__ methods
    of the lock are exposed, so "with self:" can be used instead of "with
    self.lock:". For convenience, packet handlers are called in a such
    context; if sections explicitly need not to be protected, manual calls
    to self.lock.release() and self.lock.acquire() become necessary.
    Note that, to actually take effect, changes to the roomname, nickname
    and passcode attributes must be peformed by using the corresponding
    set_*() methods (or by performing the necessary actions oneself).
    Remember to call the parent class' methods as well, because some of its
    interna are implemented there!

    Other attributes (not assignable by keyword arguments):
    cmdid       : ID of the next command packet to be sent. Used internally.
    callbacks   : Mapping of command ID-s to callables; used to implement
                  reply callbacks. Invoked after generic handlers.
    eff_nickname: The nick-name as the server returned it. May differ from
                  the one sent (truncation etc.).
    lock        : Attribute access lock. Must be acquired whenever an
                  attribute is changed, or when multiple accesses to an
                  attribute should be atomic.
    """

    def __init__(self, **config):
        """
        __init__(self, **config) -> None

        Constructor. See class docstring for usage.
        """
        self.url_template = config.get('url_template', URL_TEMPLATE)
        self.roomname = config.get('roomname', None)
        self.nickname = config.get('nickname', None)
        self.passcode = config.get('passcode', None)
        self.retry_count = config.get('retry_count', 4)
        self.retry_delay = config.get('retry_delay', 10)
        self.handlers = config.get('handlers', {})
        self.cmdid = 0
        self.callbacks = {}
        self.eff_nickname = None
        self.lock = threading.RLock()
        # Actual connection.
        self._connection = None
        # Whether someone is poking the connection.
        self._connecting = False
        # Condition variable to serialize all on.
        self._conncond = threading.Condition(self.lock)
        # Whether the session was properly initiated.
        self._logged_in = False

    def __enter__(self):
        return self.lock.__enter__()
    def __exit__(self, *args):
        return self.lock.__exit__(*args)

    def _make_connection(self, url):
        """
        _make_connection(url) -> JSONWebSocket

        Actually connect to url.
        Returns the object produced, or raises an exception.
        Can be hooked by subclasses.
        """
        return JSONWebSocket(websocket.create_connection(url))

    def _attempt(self, func):
        """
        _attempt(func) -> object

        Attempt to run func; if it raises an exception, re-try using the
        specified parameters (retry_count and retry_delay).
        Func is called with two arguments, the zero-based trial counter,
        and amount of re-tries that will be attempted.
        If the last attempt fails, the exception that indicated the
        failure is raised.
        If the function call succeeds, the return value of func is passed
        out.
        """
        with self.lock:
            count, delay = self.retry_count, self.retry_delay
        for i in range(count + 1):
            if i: time.sleep(delay)
            try:
                return func(i, count)
            except Exception:
                if i == count:
                    raise
                continue

    def _connect(self):
        """
        _connect() -> None

        Internal back-end for connect(). Takes care of synchronization.
        """
        with self._conncond:
            if self.roomname is None:
                raise NoRoomError('No room specified')
            while self._connecting:
                self._conncond.wait()
            if self._connection is not None:
                return
            self._connecting = True
            url = self.url_template.format(self.roomname)
        conn = None
        try:
            conn = self._attempt(lambda c, a: self._make_connection(url))
        finally:
            with self._conncond:
                self._connecting = False
                self._connection = conn
                if conn is not None:
                    self.handle_connect()
                self._conncond.notifyAll()

    def _disconnect(self):
        """
        _disconnect() -> None

        Internal back-end for close(). Takes care of synchronization.
        """
        with self._conncond:
            while self._connecting:
                self._conncond.wait()
            conn = self._connection
            self._connection = None
            if self._logged_in:
                self.handle_logout(True)
                self._logged_in = False
            self.handle_close(True)
            self._conncond.notifyAll()
        if conn is not None:
            conn.close()

    def _reconnect(self):
        """
        _reconnect() -> None

        Considering the current connection to be broken, discard it
        forcefully (unless another attempt to re-connect is already
        happening), and try to connect again (only once).
        """
        with self._conncond:
            if not self._connecting:
                self._connection = None
            while self._connecting:
                self._conncond.wait()
            if self._connection is not None:
                return
            if self._logged_in:
                self.handle_logout(False)
                self._logged_in = False
            self.handle_close(False)
            self._connecting = True
        conn = None
        try:
            conn = self._make_connection(url)
        finally:
            with self._conncond:
                self._connecting = False
                self._connection = conn
                if conn is not None:
                    self.handle_connect()
                self._conncond.notifyAll()

    def connect(self):
        """
        connect() -> None

        Connect to the configured room.
        Return instantly if already connected.
        Raises a NoRoomError is no room is specified, or a
        websocket.WebSocketException if the connection attempt(s) fail.
        Re-connections are tried.
        """
        self._connect()

    def close(self):
        """
        close() -> None

        Close the current connection (if any).
        Raises a websocket.WebSocketError is something unexpected happens.
        """
        self._disconnect()

    def reconnect(self):
        """
        reconnect() -> None

        Disrupt the current connection (if any) and estabilish a new one.
        Raises a NoRoomError if no room to connect to is specified.
        Raises a websocket.WebSocketException if the connection attempt
        fails.
        """
        self.close()
        self.connect()

    def get_connection(self):
        """
        get_connection() -> JSONWebSocket

        Obtain a reference to the current connection. Waits for all pending
        connects to finish. May return None if not connected.
        """
        with self._conncond:
            while self._connecting:
                self._conncond.wait()
            return self._connection

    def handle_connect(self):
        """
        handle_connect() -> None

        Called after a connection attempt succeeded.
        """
        pass

    def handle_close(self, ok):
        """
        handle_close(ok) -> None

        Called after a connection failed (or was normally closed).
        The ok parameter tells whether the close was normal (ok is true)
        or abnormal (ok is false).
        """
        pass

    def recv_raw(self, retry=True):
        """
        recv_raw(retry=True) -> object

        Receive a single object from the server, and return it.
        May raise a websocket.WebSocketException, or a NoConnectionError
        if not connected.
        If retry is true, the operation will be re-tried (after
        re-connects) before failing entirely.
        """
        if retry:
            return self._attempt(lambda c, a: self.recv_raw(False))
        conn = self.get_connection()
        if conn is None:
            raise NoConnectionError('Not connected')
        return conn.recv()

    def send_raw(self, obj, retry=True):
        """
        send_raw(obj, retry=True( -> object

        Try to send a single object over the connection.
        My raise a websocket.WebSocketException, or a NoConnectionError
        if not connected.
        If retry is true, the operation will be re-tried (after
        re-connects) before failing entirely.
        """
        if retry:
            return self._attempt(lambda c, a: self.send_raw(obj, False))
        conn = self.get_connection()
        if conn is None:
            raise NoConnectionError('Not connected')
        return conn.send(obj)

    def handle(self, packet):
        """
        handle(packet) -> None

        Handle a single packet.
        After wrapping structures in the reply into the corresponding
        record classes, handle_any(), built-in handlers, generic type
        handlers, and call-backs are invoked (in that order).
        """
        try:
            packet = self._postprocess_packet(packet)
        except KeyError:
            pass
        with self.lock:
            # Global handler.
            self.handle_any(packet)
            # Built-in handlers
            p, t = packet, packet.get('type')
            if   t == 'bounce-event'      : self.on_bounce_event(p)
            elif t == 'disconnect-event'  : self.on_disconnect_event(p)
            elif t == 'edit-message-event': self.on_edit_message_event(p)
            elif t == 'hello-event'       : self.on_hello_event(p)
            elif t == 'join-event'        : self.on_join_event(p)
            elif t == 'login-event'       : self.on_login_event(p)
            elif t == 'logout-event'      : self.on_logout_event(p)
            elif t == 'network-event'     : self.on_network_event(p)
            elif t == 'nick-event'        : self.on_nick_event(p)
            elif t == 'part-event'        : self.on_part_event(p)
            elif t == 'ping-event'        : self.on_ping_event(p)
            elif t == 'send-event'        : self.on_send_event(p)
            elif t == 'snapshot-event'    : self.on_snapshot_event(p)
            # Special built-in handler.
            if i is not None and t.endswith('-reply'): self.handle_reply(p)
            # Typeless handlers
            self._run_handlers(None, packet)
            # Type handlers
            tp = packet.get('type')
            if tp: self._run_handlers(tp, packet)
            # Call-backs
            cb = self.callbacks.pop(packet.get('id'), None)
            if callable(cb): cb(packet)

    def _postprocess_packet(self, packet):
        """
        _postprocess_packet(packet) -> dict

        Wrap structures in packet into the corresponding wrapper classes.
        The '_self' item of packet is set to the HeimEndpoint instance the
        method is called on.
        Used by handle(). May or may not modify the given dict, or any of
        its members, as well as return an entirely new one, as it actually
        does.
        May raise a KeyError if the packet is missing required fields.
        """
        tp = packet['type']
        if tp in ('get-message-reply', 'send-reply', 'edit-message-reply',
                  'edit-message-event', 'send-event'):
            packet['data'] = self._postprocess_message(packet['data'])
        elif tp == 'log-reply':
            data = packet['data']
            data['log'] = [self._postprocess_message(m) for m in data['log']]
        elif tp == 'who-reply':
            packet['data'] = [self._postprocess_sessionview(e)
                              for e in packet['data']]
        elif tp == 'hello-event':
            data = packet['data']
            data['session'] = self._postprocess_sessionview(data['session'])
            # TODO: account -> PersonalAccountView
        elif tp in ('join-event', 'part-event'):
            packet['data'] = self._postprocess_sessionview(packet['data'])
        elif tp == 'snapshot-event':
            data = packet['data']
            data['listing'] = [self._postprocess_sessionview(e)
                               for e in data['listing']]
            data['log'] = [self._postprocess_message(m) for m in data['log']]
        packet['_self'] = self
        return Packet(packet)

    def _postprocess_message(self, msg):
        """
        _postprocess_message(msg) -> dict

        Wrap a Message structure into the corresponding wrapper class.
        Used by _postpocess_packet().
        """
        msg['sender'] = self._postprocess_sessionview(msg['sender'])
        return Message(msg)

    def _postprocess_sessionview(self, view):
        """
        _postprocess_sessionview(view) -> dict

        Wrap a SessionView structure into the corresponding wrapper class.
        Used by _postpocess_packet().
        """
        return SessionView(view)

    def handle_any(self, packet):
        """
        handle_any(packet) -> None

        Handle a single post-processed packet.
        Can be used as a catch-all handler; called by handle().
        """
        pass

    def handle_reply(self, packet):
        """
        handle_reply(packet) -> None

        Handle an arbitrary command reply.
        Useful for checking command replies non-specifically. Called by
        handle().
        """
        if packet.type == 'nick-reply':
            self.eff_nickname = packet.to

    def on_bounce_event(self, packet):
        """
        on_bounce_event(packet) -> None

        Built-in event packet handler. Used internally for the login
        procedure.
        """
        if ('passcode' in packet.data.get('auth_options', ()) and
                self.passcode is not None):
            self.set_passcode()

    def on_disconnect_event(self, packet):
        """
        on_disconnect_event(packet) -> None

        Built-in event packet handler. Used internally for the login
        procedure.
        """
        # Gah! Hardcoded messages!
        if packet.get('reason') == 'authentication changed':
            self.reconnect()

    def on_hello_event(self, packet):
        """
        on_hello_event(packet) -> None

        Built-in event packet handler.
        """
        pass

    def on_join_event(self, packet):
        """
        on_join_event(packet) -> None

        Built-in event packet handler.
        """
        pass

    def on_login_event(self, packet):
        """
        on_login_event(packet) -> None

        Built-in event packet handler.
        """
        pass

    def on_logout_event(self, packet):
        """
        on_logout_event(packet) -> None

        Built-in event packet handler.
        """
        pass

    def on_network_event(self, packet):
        """
        on_network_event(packet) -> None

        Built-in event packet handler.
        """
        pass

    def on_nick_event(self, packet):
        """
        on_nick_event(packet) -> None

        Built-in event packet handler.
        """
        pass

    def on_edit_message_event(self, packet):
        """
        on_edit_message_event(packet) -> None

        Built-in event packet handler.
        """
        pass

    def on_part_event(self, packet):
        """
        on_part_event(packet) -> None

        Built-in event packet handler. Used internally for the login
        procedure.
        """
        pass

    def on_ping_event(self, packet):
        """
        on_ping_event(packet) -> None

        Handle a ping-event with a ping-reply.
        The only client-side reply required by the protocol.
        """
        self.send_packet('ping-reply', time=packet.get('time'))

    def on_send_event(self, packet):
        """
        on_send_event(packet) -> None

        Built-in event packet handler.
        """
        pass

    def on_snapshot_event(self, packet):
        """
        on_snapshot_event(packet) -> None

        Built-in event packet handler.
        """
        self.handle_login()
        self._logged_in = True
        self.set_nickname()

    def _run_handlers(self, pkttype, packet):
        """
        _run_handlers(pkttype, packet) -> None

        Run the handlers for type pkttype on packet. pkttype must be not the
        same as the type of packet.
        """
        with self.lock:
            for h in self.handlers.get(pkttype, ()):
                h(packet)

    def handle_login(self):
        """
        handle_login() -> None

        Called when a session is initialized (but before setting the
        nick-name, if any; after handle_connect()), or after a successful
        re-connect. A session may not be estabilished at all.
        """
        pass

    def handle_logout(self, ok):
        """
        handle_logout(ok) -> None

        Called when a session ends or before a re-connect; before
        handle_close().
        """
        pass

    def handle_single(self):
        """
        handle_single() -> None

        Receive and process a single packet.
        """
        self.handle(self.recv_raw())

    def handle_loop(self):
        """
        handle_loop() -> None

        Receive packets until the connection collapses.
        """
        while 1: self.handle_single()

    def add_handler(self, pkttype, handler):
        """
        add_handler(pkttype, handler) -> None

        Register handler for handling packets of type pkttype.
        """
        with self.lock:
            l = self.handlers.setdefault(pkttype, [])
            if handler not in l: l.append(handler)

    def remove_handler(self, handler):
        """
        remove_handler(handler) -> None

        Remove any bindings of handler.
        """
        with self.lock:
            for e in self.handlers.values():
                e.remove(handler)

    def set_callback(self, id, cb):
        """
        set_callback(id, cb) -> None

        Set the callback for the given message ID. Override the previously
        set one, or, if cb is None, remove it.
        """
        with self.lock:
            if cb is None:
                self.callbacks.pop(id, None)
            else:
                self.callbacks[id] = cb

    def send_packet_raw(self, type, callback=None, data=None):
        """
        send_packet_raw(type, callback, data) -> str

        Send a packet to the server.
        Differently to send_packet(), keyword arguments are not used,
        and arbitrary data can therefore be specified. Returns the
        serial ID of the packet sent.
        """
        with self.lock:
            cmdid = str(self.cmdid)
            self.cmdid += 1
            if callback is not None:
                self.callbacks[cmdid] = callback
        pkt = {'type': type, 'id': cmdid}
        if data is not None: pkt['data'] = data
        self.send_raw(pkt)
        return cmdid

    def send_packet(_self, _type, _callback=None, **_data):
        """
        send_packet(_type, _callback=None, **_data) -> str

        Send a packet to the server.
        The packet type is specified as a positional argument, an optional
        callback for handling the server's reply may be specified as well;
        the payload of the packet is passed as keyword arguments. Returns
        the sequential ID of the packet sent.
        May raise any exception send_raw() raises.
        """
        return _self.send_packet_raw(_type, _callback, _data)

    def set_roomname(self, room=None):
        """
        set_roomname(room=None) -> None

        Set the roomname attribute, and (as a "side effect") connect to
        that room (if already connected). If room is None, perform no
        action.
        """
        if room is None: return
        with self.lock:
            self.roomname = room
            if self.get_connection() is not None:
                reconn = True
            else:
                reconn = False
        if reconn: self.reconnect()

    def set_nickname(self, nick=None):
        """
        set_nickname(nick=None) -> msgid or None

        Set the nickname attribute to nick (unless nick is Ellipsis), and
        send a corresponding command to the server (if connected, and
        nickname is non-None).
        Returns the sequential message ID if a command was sent.
        """
        with self.lock:
            # Ellipsis FTW!
            if nick is not Ellipsis: self.nickname = nick
            if (self.get_connection() is not None and
                    self.nickname is not None):
                return self.send_packet('nick', name=self.nickname)

    def set_passcode(self, code=Ellipsis):
        """
        set_passcode(code=Ellipsis) -> msgid or None

        Set the passcode attribute to code (unless code is Ellipsis), and
        send a corresponding command to the server (if connected, and
        passcode is non-None).
        Returns the sequential message ID if a command was sent.
        """
        with self.lock:
            if code is not Ellipsis: self.passcode = code
            if (self.get_connectin() is not None and
                    self.passcode is not None):
                return self.send_packet('auth', type='passcode',
                                        passcode=self.passcode)

class LoggingEndpoint(HeimEndpoint):
    """
    LoggingEndpoint(**config) -> New instance.

    A HeimEndpoint that maintains a user list and chat logs on demand.
    See HeimEndpoint on configuration details.

    Additional attributes (configurable through keyword arguments):
    log_users   : Maintain a user list (if false, it will be empty; defaults
                  to False).
    log_messages: Maintain a chat log (if false, it will be empty; defaults
                  to False).

    If log_users or log_messages are changed during operation, the values in
    the corresponding list (see below) cannot be relied upon.

    ...More additional attributes:
    users   : A UserList, holding the current user list (or nothing).
    messages: A MessageTree, holding the chat logs (in "natural" order;
              or nothing).
    """

    def __init__(self, **config):
        "Constructor. See class docstring for details."
        HeimEndpoint.__init__(self, **config)
        self.log_users = config.get('log_users', False)
        self.log_messages = config.get('log_messages', False)
        self.users = UserList()
        self.messages = MessageTree()

    def handle_close(self, ok):
        "See HeimEndpoint.handle_close() for details."
        HeimEndpoint.handle_close(self, ok)
        self.users.clear()
        self.messages.clear()

    def handle_any(self, packet):
        "See HeimEndpoint.handle_any() for details."
        HeimEndpoint.handle_any(self, packet)
        if self.log_users:
            if packet.type == 'who-reply':
                self.users.add(*packet.data)
            elif packet.type == 'snapshot-event':
                self.users.add(*packet.data['listing'])
            elif packet.type == 'network-event':
                if packet.data['type'] == 'partition':
                    self.users.remove_matching({
                        'server_id': packet.data['server_id'],
                        'server_era': packet.data['server_era']})
            elif packet.type == 'nick-event':
                usr = self.users.for_session_id(packet.data['session_id'])
                usr.name = packet.data['to']
            elif packet.type == 'join-event':
                self.users.add(packet.data)
            elif packet.type == 'part-event':
                self.users.remove(packet.data)
        if self.log_messages:
            if packet.type in ('get-message-reply', 'send-reply',
                               'edit-message-reply', 'edit-message-event',
                               'send-event'):
                self.messages.add(packet.data)
            elif packet.type == 'log-reply':
                self.messages.add(*packet.data['log'])

    def refresh_users(self):
        """
        refresh_users() -> None

        Clear the user list, and send a request to re-fill it.
        Note that the actual user list update will happen asynchronously.
        Returns the ID of the packet sent.
        """
        with self.lock:
            self.users.clear()
            return self.send_packet('who')

    def refresh_logs(self, n=100):
        """
        refresh_logs(n=100) -> None

        Clear the message logs, and send a request to re-fill them
        (partially). n is the amount of messages to request.
        Note that the actual logs update will happen asynchronously.
        Returns the ID of the packet sent.
        """
        with self.lock:
            self.messages.clear()
            return self.send_packet('log', n=n)
