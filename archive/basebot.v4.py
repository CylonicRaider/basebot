# -*- coding: ascii -*-

# Base class for Euphoria chat bots.
# Based on a closed GitHub project.
# This code is in the public domain.

# Modules - Standard library
import sys, os, re, time
import json
import logging

try:
    import errno
    ECONNRESET = errno.ECONNRESET
except (ImportError, AttributeError):
    errno, ECONNRESET = None, None
import threading

# Modules - Additional. Must be installed.
import websocket
from websocket import WebSocketException as WSException

# Regex for mentions.
MENTION_RE = re.compile('\B@([^\s]+?(?=$|[,.!?:;&\'\s]|&#39;|&quot;|&amp;))')
# Regex for whitespace
WHITESPACE_RE = re.compile('[^\S]')

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
    'sender_id': ID of the sender of the message.
    'session'  : Session ID of the sender.
    'content'  : The content of the message.
    'id'       : The ID of the message (like for replies).
    'parent'   : The ID of the parent of the message.
    'mentions' : A set of all names @-mentioned in the message.
    """
    d = m.get('data', {})
    s = d.get('sender', {})
    c = d.get('content')
    p = d.get('parent')
    if not p: p = None # In case p is the empty string.
    return {'id': d.get('id'), 'parent': p, 'content': c,
            'sender': s.get('name'), 'sender_id': s.get('id'),
            'session': s.get('session_id'),
            'mentions': set(scan_mentions(c))}

# Main class.
class Bot:
    """
    Bot(roomname, password=None) -> new instance

    roomname: The name of the room to join.
    password: Password for private rooms.

    Interesting instance variables:
    nickname: The "pre-configured" nickname. Set to the global variable
              NICK_NAME as default. You can change it after construction.

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
        self.conn = None
        self.send_callbacks = {}
        self.users = {}
        self.users_nick = {}
        self.msgid = 0
        self.logger = logging

    def connect(self, _n=3, _exc=None):
        """
        connect() -> None

        Try to connect to the configured room.
        Re-connection attempts are made two times if the connection
        fails, after that, an exception is raised.
        """
        if _n <= 0: raise _exc[1]
        try:
            self.conn = websocket.create_connection('wss://euphoria.io/'
                'room/%s/ws' % self.roomname)
        except WSException:
            self.logger.exception('Connection lost; will retry '
                'in 3 seconds...')
            time.sleep(3)
            self.connect(_n - 1, sys.exc_info())
        except IOError as e:
            self.logger.exception('I/O error; will retry '
                'in 3 seconds...')
            time.sleep(3)
            self.connect(_n - 1, sys.exc_info())
        else:
            self.msgid = 0

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
        self.logger.info('Logging in to room %r...' % self.roomname)
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
            user['normname'] = WHITESPACE_RE.sub('', user['name'])
        else:
            user.setdefault('name', '')
            user.setdefault('normname', '')
        self.users_nick[user['name']] = user
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

        Internal handler for join events.
        """
        data = message.get('data')
        if not data or not 'id' in data: return
        self.update_user(data['session_id'], id=data.get('id'),
                         name=data.get('name'), online=True)

    def handle_partevent(self, message):
        """
        handle_partevent(message) -> None

        Internal handler for part events.
        """
        data = message.get('data')
        if not data or not 'session_id' in data: return
        self.update_user(data['session_id'], id=data.get('id'),
                         name=data.get('name'), online=False)

    def handle_nickevent(self, message):
        """
        handle_nickevent(message) -> None

        Internal handler for nickname changes.
        """
        data = message.get('data')
        if not data or not 'id' in data: return
        self.update_user(data['session_id'], id=data.get('id'),
                         name=data.get('to'), last_seen=Ellipsis)

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

        Performs preparations for the bot's main loop.
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

def run_main(cls, argv, **config):
    """
    Convenience function for startng bots.

    See source code for details.
    """
    # Apply arguments.
    if argv is not None:
        # Print usage if used incorrectly.
        if len(argv) < 1 or len(argv) > 2:
            print ('USAGE: %s roomname [password]\n' % (
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
