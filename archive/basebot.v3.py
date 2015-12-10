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
try:
    import threading
except ImportError:
    threading = None

# Modules - Additional. Must be installed.
import websocket
from websocket import WebSocketException as WSException

# Regex for mentions.
MENTION_RE = re.compile('\B@([^\s]+?(?=$|[,.!?:;&\'\s]|&#39;|&quot;|&amp;))')

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
    'sender'  : Nickname of the sender of the message.
    'content' : The content of the message.
    'id'      : The ID of the message (like for replies).
    'parent'  : The ID of the parent of the message.
    'mentions': A set of all names @-mentioned in the message.
    """
    d = m.get('data', {})
    c = d.get('content')
    p = d.get('parent')
    if not p: p = None
    return {'id': d.get('id'), 'parent': p, 'content': c,
            'sender': d.get('sender', {}).get('name'),
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

        See also: send_msg()
        """
        self.conn.send(data)
        self.logger.debug('> %r' % (data,))

    def send_msg(self, _type, **message):
        """
        send_msg(type, **message) -> id

        Send a message with the given type, the contents of message as
        data, and an sequentially generated ID. The ID of the message
        sent is returned; it is a string.

        See also: send_chat() as a convenient was of sending chat messages.
        """
        msg = {'id': str(self.msgid), 'type': _type, 'data': message}
        self.send_raw(json.dumps(msg))
        i = str(self.msgid)
        self.msgid += 1
        return i

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

        See also: extract_message_data()
        """
        # Extract the id from the reply.
        pid = message.get('id')
        # Try to look up a call-back for that.
        cb = self.send_callbacks.pop(pid, None)
        # Call it if possible.
        if callable(cb): cb(extract_message_data(message), message)

    def handle_sendevent(self, message):
        """
        handle_sendevent(message) -> None

        Extracts some interesting data from the event and calls handle_chat().

        See also: handle_chat() extract_message_data()
        """
        self.handle_chat(extract_message_data(message), message)

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
        if threading is None:
            self.lock = None
        else:
            self.lock = threading.RLock()

    def __enter__(self):
        if self.lock is not None:
            return self.lock.__enter__()
    def __exit__(self, *args):
        if self.lock is not None:
            return self.lock.__exit__(*args)

    def send_msg(self, _type, **data):
        """
        send_msg(self, type, **data) -> id

        See Bot.send_msg() for usage.
        """
        with self:
            return Bot.send_msg(self, _type, **data)

def run_main(cls, argv, **config):
    """
    Convenience function for startng bots.

    See source code for details.
    """
    # Apply arguments.
    if argv is not None:
        # Log file.
        if argv and argv[0] == '--logfile':
            config['logfile'] = Ellipsis
            argv = argv[1:]
        # Print usage if used incorrectly.
        if len(argv) < 1 or len(argv) > 2:
            print ('USAGE: %s [--logfile] roomname [password]\n' % (
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
