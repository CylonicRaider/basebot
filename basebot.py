# -*- coding: ascii -*-

"""
Bot library for euphoria.io.

For quick and simple bots, see run_minibot(); for more sophisticated ones,
use ThreadedBot (Bot is very similar, but not thread-safe) with run_main().
"""

# Base class for Euphoria chat bots.
# Based on a closed GitHub project.
# See http://github.com/euphoria-io/heim/wiki for further information
# for developers.
# This code is in the public domain.

# Modules - Standard library
import sys, os, re, time
import json
import logging
import threading

# Modules - Additional. Must be installed.
import websocket
from websocket import WebSocketException as WSException

# Regex for mentions.
MENTION_RE = re.compile('\B@([^\s]+?(?=$|[,.!?:;&\'\s]|&#39;|&quot;|&amp;))')

# Regex for whitespace.
WHITESPACE_RE = re.compile('[^\S]')

# Format string %-instantiated with the room name to form the URL
# to connect to.
ROOM_FORMAT = 'wss://euphoria.io/room/%s/ws'

# Compatibility.
try:
    _basestring = basestring
except NameError:
    _basestring = str

def spawn_thread(func, *args, **kwds):
    """
    spawn_thread(func, *args, **kwds) -> Thread

    Run func(*args, **kwds) in a daemonic background thread.
    The Thread object created is returned.
    """
    thr = threading.Thread(target=func, args=args, kwargs=kwds)
    thr.setDaemon(True)
    thr.start()
    return thr

def scan_mentions(s):
    """
    scan_mentions(s) -> list

    Scan the given message for @-mentions and return them as a list,
    preserving the order.
    """
    return MENTION_RE.findall(s)
def extract_message_data(m):
    """
    extract_message_data(m) -> dict

    Extract possibly interesting data from the message m as a dictionary.
    Included items:
    'sender'   : Nickname of the sender of the message.
    'nsender'  : Normalized nickname of the sender of the message.
    'sender_id': ID of the sender of the message.
    'session'  : Session ID of the sender.
    'content'  : The content of the message.
    'id'       : The ID of the message (like for replies).
    'parent'   : The ID of the parent of the message.
    'mentions' : A set of all names @-mentioned in the message.
    'raw'      : The raw message.

    See also: normalize_nick() for nickname normalization.
    """
    d = m.get('data') or {}
    s = d.get('sender', {})
    c = d.get('content')
    p = d.get('parent')
    n = s.get('name')
    if not p: p = None # In case p is the empty string.
    return {'id': d.get('id'), 'parent': p, 'content': c,
            'sender': n, 'nsender': normalize_nick(n) if n else None,
            'sender_id': s.get('id'), 'session': s.get('session_id'),
            'mentions': set(scan_mentions(c)), 'raw': m}
def normalize_nick(nick):
    """
    normalize_nick(nick) -> str

    Remove whitespace from the given nick, and perform any other
    normalizations with it.
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

# Main class.
class Bot(object):
    """
    Bot(roomname, password=None) -> new instance

    roomname: The name of the room to join.
    password: Password for private rooms.

    Interesting instance variables:
    nickname: The "pre-configured" nickname. Set to the class attribute
              NICK_NAME as default. You can change it after construction.
    roomname: The name of the room this bot is in.
    password: The passcode for the current room (or None).
    logger  : The logger associated with this instance.
    send_callbacks: A mapping of message IDs to call-backs.
                    See handle_sendreply() for details.
    room_format   : A format string %-instantiated with the room name to
                    form the URL to connect to. If None, the environment
                    variable "BASEBOT_ROOM_FORMAT" is tried, if that does
                    not exist, the module-level default ROOM_FORMAT is
                    taken.
    rename_logger : Allows to re-assign the logger instance variable
                    when the room changes (will use the result of
                    logging.getLogger(roomname) as the logger). If not set,
                    the instance variable logger will never be changed.
    starttime     : The floating-point UNIX timestamp of the instantiation
                    of the bot. Used for !uptime.

    Interesting class variables (both to be overridden by subclasses):
    NAME     : The "name" of the bot to be used for logging (and similar
               purposes).
    NICK_NAME: The default nickname for new instances of the bot.

    Class usage:
    After creating an instance, the instance can be configured, and after
    that let be run by calling run().
    >>> b = BotClass(roomname)
    >>> b.run()
    """

    # Name for logging.
    NAME = 'bot'

    # Default nick-name for bots.
    NICK_NAME = 'bot'

    def __init__(self, roomname, password=None, **kwds):
        """
        __init__(roomname, password=None)

        See class docstring for usage.
        """
        self.roomname = roomname
        self.password = password
        self.nickname = self.NICK_NAME
        self.starttime = time.time()
        self.room_format = None
        self.conn = None
        self.send_callbacks = {}
        self.users = {}
        self.users_nick = {}
        self.msgid = 0
        self.rename_logger = True
        self.logger = logging
        self._exiting = False

    def _connect(self, _n=6, _exc=None):
        """
        _connect() -> None

        This is an internal back-end for connect().
        Don't override this method.
        """
        if _n <= 0: raise _exc[1]
        try:
            if self.room_format is None:
                room_format = os.environ.get('BASEBOT_ROOM_FORMAT',
                    ROOM_FORMAT)
            else:
                room_format = self.room_format
            url = room_format % self.roomname
            self.logger.info('Connecting to %s...' % url)
            self.conn = websocket.create_connection(url)
            if self.rename_logger:
                self.logger = logging.getLogger(self.roomname)
        except WSException:
            self.logger.exception('Connection lost; will retry '
                'in 10 seconds...')
            time.sleep(10)
            self._connect(_n - 1, sys.exc_info())
        except IOError as e:
            self.logger.exception('I/O error; will retry '
                'in 10 seconds...')
            time.sleep(10)
            self._connect(_n - 1, sys.exc_info())
        else:
            self.msgid = 0

    def connect(self):
        """
        connect() -> None

        Try to connect to the configured room.
        Re-connection attempts are made five times if the connection
        fails, after that, an exception is raised.

        This method is called to estabilish a connection to a (new)
        room; you can override it you need to hook it.
        """
        return self._connect()

    def disconnect(self, final=False):
        """
        disconnect(final=False) -> None

        Break this bot's connection. If final is false, nothing in
        particular happens, and the connection is estabilished
        again after some time. If final is true, a flag is set
        indicating the bot should not try to re-connect, but rather
        exit.
        This method is asynchronous. Use other means to determine
        when the bot is online again.
        """
        if final: self._exiting = True
        self.conn.close()

    def exit(self):
        """
        exit() -> None

        Shorthand for disconnect(True).
        """
        return disconnect(True)

    def change_room(self, roomname, password=None):
        """
        change_room(self, roomname, password=None) -> None

        Switch this bot to another room, so, make is disconnect from
        the current room, and re-connect to another one.
        This method is asynchronous. Use other means to determine
        when the bot is online again.
        """
        self.roomname = roomname
        self.password = password
        self.disconnect()

    def send_raw(self, data):
        """
        send_raw(data) -> None

        Send data into the connection without further modofication.
        Use json.dumps() to send JSON data.

        See also: send_msg_ex() send_msg()
        """
        self.conn.send(data)
        self.logger.debug('> %r' % (data,))

    def send_msg_ex(self, type, data):
        """
        send_msg_ex(type, data) -> id

        Send a message with the given type, the contents of message as
        data, and an sequentially generated ID. The ID of the message
        sent is returned; as of now, it is a string.

        See also: send_msg() as a slightly more convenient variant.
                  send_chat() as a convenient way of sending chat messages.
        """
        msg = {'id': str(self.msgid), 'type': type, 'data': data}
        self.send_raw(json.dumps(msg))
        i = str(self.msgid)
        self.msgid += 1
        return i

    def send_msg(self_, type_, **message_):
        """
        send_msg(type_, **message_) -> id

        Thin wrapper around send_msg_ex(). Uses keyword arguments instead
        of an explicit dictionary.

        See also: send_msg_ex() if one of the message fields must be named
                                self_, type_, or message_.
                  send_chat() as a convenient ways of sending chat messages.
        """
        return self_.send_msg_ex(type_, message_)

    def send_chat(self, content, parent=None, **additional):
        """
        send_chat(content, parent=None, **additional) -> id

        Prepare a chat message, and send it. The message content consists
        of content and parent under their respective names, and all items
        from additional.
        """
        if self.nickname is None: return
        self.logger.info('Sending chat: %r' % (content,))
        return self.send_msg('send', content=content, parent=parent,
                             **additional)

    def login(self):
        """
        login() -> None

        Log in to the configured chatroom. connect() must have been called
        first. If a password was given, try to authenticate using it. Set
        the configured nickname additionally.
        """
        self.logger.info('Logging in (to room %r)...' % self.roomname)
        if self.password is not None:
            self.send_msg('auth', type='passcode',
                          passcode=self.password)
        self.set_nickname()

    def set_nickname(self, name=None):
        """
        set_nickname(name=None) -> id

        Set the specified nickname. If name is None, set the pre-configured
        nickname. If THAT is None, do not send a nickname at all. The
        pre-configured nickname is updated to reflect the change.
        """
        if name is None: name = self.nickname
        if name is None: return
        self.nickname = name
        self.logger.info('Setting nickname: %r' % (name,))
        return self.send_msg('nick', name=name)

    def handle_incoming(self, message):
        """
        handle_incoming(message) -> None

        Handler for incoming messages. Calls appropriate sub-handlers
        depending on the message type, in particular handle_sendevent().

        See also: handle_sendevent()
        """
        tp = message.get('type')
        if tp == 'ping-event':
            self.handle_ping(message)
        elif tp == 'send-reply':
            self.handle_sendreply(message)
        elif tp == 'send-event':
            self.handle_sendevent(message)
        elif tp in ('snapshot-event', 'who-reply'):
            self.handle_who(message)
        elif tp == 'join-event':
            self.handle_joinevent(message)
        elif tp == 'part-event':
            self.handle_partevent(message)
        elif tp == 'nick-event':
            self.handle_nickevent(message)

    def handle_ping(self, message):
        """
        handle_ping(message) -> None

        Handles a ping from the server by sending a reply.
        """
        # Send a reply so the server does not drop the connection.
        self.send_msg('ping-reply', time=int(time.time()))

    def handle_sendreply(self, message):
        """
        handle_sendreply(message) -> None

        Handles a send reply by looking up a call-back in the sent_messages
        instance variable, and calling it if present. The parameters are:
        (1) Message data from extract_message_data(), and
        (2) The message itself.
        self.users is updated *after* the call-back call, because the data
        to be inserted is trivial, and the last activity of the user
        might be interesting.

        See also: extract_message_data()
        """
        # Extract data from the reply.
        md = extract_message_data(message)
        # Try to look up a call-back for that.
        cb = self.send_callbacks.pop(md['id'], None)
        # Call it if possible.
        if callable(cb): cb(md, message)
        # Update the user "database".
        self.update_user(md['session'], last_seen=Ellipsis,
                         id=md['sender_id'], name=md['sender'],
                         last_message=md['id'])

    def handle_sendevent(self, message):
        """
        handle_sendevent(message) -> None

        Extracts some interesting data from the event and calls
        handle_chat().
        See handle_sendreply() about self.users.

        See also: handle_chat() extract_message_data()
        """
        # Extract data
        md = extract_message_data(message)
        # Call the high-level handler
        self.handle_chat(md, message)
        # Update self.users
        self.update_user(md['session'], last_seen=Ellipsis,
                         id=md['sender_id'], name=md['sender'],
                         last_message=md['id'])

    def update_user(self, session, **data):
        """
        update_user(session, **data) -> dict

        Update the user table with the given data. Used internally. The user
        dictionary is returned.
        """
        if session is None:
            self.logger.warn('update_user() with empty session ID.')
            return None
        user = self.users.setdefault(session, {})
        user['session'] = session
        user['id'] = data.get('id', user.get('id'))
        if data.get('name') and user.get('name') != data['name']:
            user['name'] = data['name']
            user['normname'] = normalize_nick(user['name'])
        else:
            user.setdefault('name', '')
            user.setdefault('normname', '')
        self.users_nick[user['normname']] = user
        if 'last_seen' in data:
            if data['last_seen'] is Ellipsis:
                user['last_seen'] = time.time()
            else:
                user['last_seen'] = data['last_seen']
        else:
            user.setdefault('last_seen', None)
        user['last_message'] = data.get('last_message',
                                        user.get('last_message'))
        user['online'] = data.get('online', user.get('online'))
        return user

    def get_user(self, session, default=None):
        """
        get_user(session, default=None) -> dict

        Return the user with the given session ID, or default if such
        a user is not known.
        """
        return self.users.get(session, default)
    def get_user_nick(self, nick, default=None):
        """
        get_user_nick(nick, default=None) -> dict

        Return the last user who posted using the given nickname,
        or default if there is no such user.
        """
        return self.users_nick.get(nick, default)

    def handle_who(self, message):
        """
        handle_who(message) -> None

        Internal handler for events containing user lists.
        """
        # Extract data
        if message.get('type') == 'who-reply':
            data = message.get('data')
        elif message.get('type') == 'snapshot-event':
            mdata = message.get('data', {})
            data = mdata.get('listing')
            if mdata:
                self.update_user(mdata.get('session_id'),
                                 name=self.nickname,
                                 id=mdata.get('identity'),
                                 online=True,
                                 last_seen=Ellipsis)
        else:
            data = None
        if not data: return
        # Process it.
        timestamp = time.time()
        for entry in data:
            if 'session_id' not in entry: continue
            self.update_user(entry['session_id'], name=entry.get('name'),
                             id=entry.get('id'), last_seen=timestamp,
                             online=True)

    def handle_joinevent(self, message):
        """
        handle_joinevent(message) -> None

        Handler for join events; updates user database.
        Be sure to call the parent class' method.
        """
        data = message.get('data')
        if not data or not 'id' in data: return
        self.update_user(data['session_id'], id=data.get('id'),
                         name=data.get('name'), online=True)

    def handle_partevent(self, message):
        """
        handle_partevent(message) -> None

        Handler for part events; updates user database.
        Be sure to call the parent class' method.
        """
        data = message.get('data')
        if not data or not 'session_id' in data: return
        self.update_user(data['session_id'], id=data.get('id'),
                         name=data.get('name'), online=False)

    def handle_nickevent(self, message):
        """
        handle_nickevent(message) -> None

        Handler for nickname change events; updates user database.
        Be sure to call the parent class' method.
        """
        data = message.get('data')
        if not data or not 'id' in data: return
        self.update_user(data['session_id'], id=data.get('id'),
                         name=data.get('to'), last_seen=Ellipsis)

    def handle_commands(self, info, message, do_ping=True, do_spec_ping=None,
                        do_uptime=True, short_help=None, long_help=None):
        """
        handle_commands(info, message, do_ping=True, do_spec_ping=None,
                        do_uptime=True, short_help=None,
                        long_help=None) -> bool

        Handler for "standard commands", that are:
        !ping        : Generic responsiveness test. Reply is a single
                       "Pong!". Controlled by the do_ping argument.
        !ping @nick  : Responsiveness test for an individual bot. Controlled
                       by the do_spec_ping argument, if that is None (or
                       omitted), do_ping is used.
        !help        : Generic help request. Responses should be short, very
                       preferably one-liners, with mention of the specific
                       help command if necessary. The response is specified
                       by short_help, if that is None, the command is
                       ignored.
        !help @nick  : Specific help request. The response is given by either
                       the long_help argument, or the short_help argument
                       if the former is None (or omitted); if both are None,
                       the command is ignored.
        !uptime @nick: Returns a message about how long the bot is running.
        Full usage of those commands is recommended.

        The method is intended to be called from handle_chat(), it returns
        whether a command has been processed.
        """
        cnt = info['content']
        if cnt == '!ping':
            if do_ping:
                self.send_chat('Pong!', info['id'])
                return True
        elif cnt == '!ping @' + self.nickname:
            if (do_ping if do_spec_ping is None else do_spec_ping):
                self.send_chat('Pong!', info['id'])
                return True
        elif cnt == '!help':
            if short_help:
                self.send_chat(short_help, info['id'])
                return True
        elif cnt == '!help @' + self.nickname:
            text = long_help or short_help
            if text:
                self.send_chat(text, info['id'])
                return True
        elif cnt == '!uptime @' + self.nickname:
            if do_uptime:
                ts = time.time()
                self.send_chat('/me is up since %s (%s)' %
                    (format_datetime(self.starttime),
                    format_delta(ts - self.starttime)), info['id'])
                return True
        return False

    def handle_chat(self, info, message):
        """
        handle_chat(info, message) -> None

        Handler for chat messages. Called from handle_sendevent().

        See also: extract_message_data() for info entries
        """
        pass

    def startup(self):
        """
        startup() -> None

        Perform preparations for the bot's main loop.
        """
        # Connect.
        self.connect()
        self.login()

    def shutdown(self):
        """
        shutdown() -> None

        Do some final actions in case the bot should shut down.
        """
        pass

    def run(self):
        """
        run() -> None

        Main loop. Calls startup() before entering the main loop,
        and shutdown() if a KeyboardInterrupt is received.
        """
        self.startup()
        while True:
            try:
                raw = self.conn.recv()
                self.logger.debug('< %r' % (raw,))
                data = json.loads(raw)
                self.handle_incoming(data)
            except WSException:
                self.logger.error('Connection lost; '
                    'reconnecting in 10sec...')
                time.sleep(10)
                if self._exiting:
                    self.shutdown()
                    break
                self.connect()
                self.login()
            except IOError as e:
                self.logger.exception('I/O error; '
                    'reconnecting in 10sec...')
                time.sleep(10)
                self.connect()
                self.login()
            except KeyboardInterrupt:
                self.shutdown()
                break

    def main(self):
        """
        main() -> None

        The "main method" of this bot. The default calls run() (and
        returns its return value).
        """
        return self.run()

class ThreadedBot(Bot):
    """
    Base class for thread-safe bots.

    Provides an additional instance member, lock, which is used to
    serialize calls to send_msg().

    See also: Bot
    """
    def __init__(self, *args, **kwds):
        """
        __init__(roomname, password=None)

        See class docstring for usage.
        """
        Bot.__init__(self, *args, **kwds)
        self.lock = threading.RLock()

    def __enter__(self):
        if self.lock is not None:
            return self.lock.__enter__()
    def __exit__(self, *args):
        if self.lock is not None:
            return self.lock.__exit__(*args)

    def connect(self):
        """
        connect() -> None

        See Bot.connect() for usage.
        """
        with self:
            return Bot.connect(self)

    def update_user(self, session, **data):
        """
        update_user(session, **data) -> dict

        See Bot.update_user() for usage.
        """
        with self:
            return Bot.update_user(self, session, **data)

    def get_user(self, session, default=None):
        """
        get_user(session, default=None) -> dict

        See Bot.get_user() for usage.
        """
        with self:
            return Bot.get_user(self, uid, default)
    def get_user_nick(self, nick, default=None):
        """
        get_user_nick(nick, default=None) -> dict

        See Bot.get_user_nick() for usage.
        """
        with self:
            return Bot.get_user_nick(self, nick, default)

    def send_msg_ex(self, type, data):
        """
        send_msg_ex(type, data) -> id

        See Bot.send_msg_ex() for usage.
        """
        with self:
            return Bot.send_msg_ex(self, type, data)

class MiniBot(ThreadedBot):
    """
    Convenience class for "mini-bots".
    See run_minibot() for more info.
    """

    def __init__(self, *args, **kwds):
        """
        See run_minibot() for arguments.
        """
        ThreadedBot.__init__(self, *args, **kwds)
        self.regexes = kwds.get('regexes', ())
        self.setup = kwds.get('setup', None)
        self.callback = kwds.get('callback', None)
        self.do_ping = kwds.get('do_ping', True)
        self.do_spec_ping = kwds.get('do_spec_ping', None)
        self.do_uptime = kwds.get('do_uptime', True)
        self.short_help = kwds.get('short_help', None)
        self.long_help = kwds.get('long_help', None)
        if self.setup: self.setup(self)

    def handle_chat(self, info, message):
        """
        See Bot.handle_chat() for details.
        """
        cnt = info['content']
        self.handle_commands(info, message, do_ping=self.do_ping,
            do_spec_ping=self.do_spec_ping, do_uptime=self.do_uptime,
            short_help=self.short_help, long_help=self.long_help)
        replies = []
        if hasattr(self.regexes, 'keys'):
            for k in self.regexes:
                rep = self._process_pair(k, self.regexes[k],
                                         info, message, True)
                if rep is not None: replies.append(rep)
        else:
            for el in self.regexes:
                rep = self._process_pair(el[0], el[1:], info, message,
                                         False)
                if rep is not None: replies.append(rep)
        for i in replies:
            self.send_chat(i, info['id'])
        if self.callback is not None:
            self.callback(self, info, message, replies)
    def _process_pair(self, key, value, info, message, is_dict):
        """
        Internal function processing regex entries.
        See the source code for reference on the exact behavior.
        """
        def group_cb(match):
            g = match.group(1)
            if g == '\\':
                return '\\'
            else:
                return m.group(int(g))
        info['self'] = self
        if is_dict and not isinstance(value, (tuple, list)):
            fargs = (value,)
        else:
            fargs = value
        if callable(key):
            fres = key(info, *fargs)
        else:
            m = re.match(key, info['content'])
            if m:
                if callable(fargs[0]):
                    fres = fargs[0](m, info, *fargs[1:])
                else:
                    fres = re.sub('\\\\([0-9]{1,2}|\\\\)',
                                  group_cb, fargs[0])
            else:
                fres = None
        return fres

def run_minibot(args, **config):
    r"""
    run_minibot(args, **config) -> MiniBot

    Convenience functin for starting mini-bots. Uses an instance of the
    MiniBot class. Configuration is done by keyword arguments:

    botname   : Name to be used for logging.
    nickname  : Nickname to assume.
    regexes   : A list/mapping of regular expressions with replacements
                allowing message processing without explicit functions.
                Can be:
                - A list of tuples, discriminated by the first element:
                  - Strings are treated as regular expressions, if the RE
                    matches a given message, the bot answers with the second
                    element of the tuple with grouping sequences (\1 etc.)
                    expanded. The second element can also be a function
                    (similarly to re.sub()), in that case it is called
                    with the match object of the key on the incoming message
                    followed by the message info dictionary (with the MiniBot
                    instance stored under key "self") and the remaining
                    tuple elements as subsequent arguments.
                  - Regular expression objects (from re.compile()) are
                    handled in the same way as strings.
                  - Functions are called with the info dictionary of the
                    message (similarly to above) as the first argument, and
                    all remaining elements of the tuple as subsequent
                    arguments. If the function returns None, the next element
                    is checked, otherwise, the return value is sent as a
                    reply.
                - A mapping:
                  - If the key is a string or a regular expression object,
                    the corresponsing value is used to produce a reply
                    (similarly to above).
                  - If the key is a function, it is called with the message
                    info dictionary as the first positional argument, and the
                    item value as the remaining positional arguments (if it
                    is a tuple), or the item value as the second position
                    argument (if it is not a tuple).
    setup       : A function called after the MiniBot instance is created. Can
                  set things up for other functions.
    callback    : A function taking the following arguments:
                  - The MiniBot instance.
                  - The message info dictinary.
                  - The raw message.
                  - A list of replies already sent by regex handlers.
    do_ping     : Boolean indicating whether to react to "!ping" commands.
                  Defaults to True.
    do_spec_ping: Boolean indicating whether to react to "!ping @nick" commands.
                  Defaults to do_ping.
    do_uptime   : Boolean indicating whether to react to "!uptime @nick" commands.
                  Defaults to True.
    short_help  : Short help, displayed as a reponse to a "!help" command.
                  If None, or not given, the command is ignored.
    long_help   : Long help; displayed as a response to a "!help @nickname"
                  command; if this is not defined, but short_help is, the
                  latter is used for both comamnds.

    See also: Bot.handle_commands() for do_ping, do_spec_ping, do_uptime, *_help.
    """
    botname = config.get('botname', Bot.NAME)
    nickname = config.get('nickname', Bot.NICK_NAME)
    if 'kwds' not in config: config['kwds'] = config
    cls = type(botname, (MiniBot,), {'NAME': botname, 'NICK_NAME': nickname})
    return run_main(cls, args, **config)

def run_main(cls, argv, **config):
    """
    run_main(cls, argv, **config) -> Bot

    Convenience function for running bots.

    argv is either a command line (which is then checked to have one argument
    and one optional one, representing the room name and the passcode for
    locked rooms) or None (then it is not processed).

    config contains further configuration:
    'args':     Argument tuple to use if argv is None.
    'kwds':     Keyword arguments to use for the bot.
    'logfile':  File name to log to. If Ellipsis, the name is
                cls.NAME + '.log'
    'loglevel': Logging level (default is logging.INFO).
    'logger':   Logger object to use.

    cls is instantiated with the given list and keyword arguments, its
    'logger' instance variable is set (depending on the arguments of
    run_main), and its main() method is called; after that, the bot is
    returned. main() can be overridden to do nothing if only the bot
    instance is needed.
    """
    # Apply arguments.
    if argv is not None:
        # Print usage if used incorrectly.
        if len(argv) < 1 or len(argv) > 2:
            print ('USAGE: %s roomname [password]' % (
                os.path.basename(sys.argv[0])))
            sys.exit(1)
        # We can just pass argv on.
        args = argv
    else:
        args = config.get('args', ())
    roomname = None if len(args) == 0 else args[0]
    kwds = config.get('kwds', {})
    # Prepare logging.
    if 'logfile' in config:
        if config['logfile'] is Ellipsis:
            logfile = cls.NAME + '.log'
        else:
            logfile = config['logfile']
    else:
        logfile = None
    if 'loglevel' in config:
        loglevel = config['loglevel']
    else:
        loglevel = logging.INFO
    logging.basicConfig(level=loglevel, format='[%(asctime)s '
        '%(name)s %(levelname)s] %(message)s', datefmt='%Y-%m-%d '
        '%H:%M:%S', filename=logfile)
    logging.info('Starting %s...' % cls.NAME)
    # Run.
    b = cls(*args, **kwds)
    l = config.get('logger')
    if l:
        b.logger = l
    elif roomname is not None:
        b.logger = logging.getLogger(roomname)
    b.run()
    return b
