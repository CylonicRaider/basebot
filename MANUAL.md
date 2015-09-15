# basebot setup manual

## Abstract

This manual covers the complete installation process of the `basebot`
library, including launching an example bot.

## Installation

1. The presence of a working [Python](http://www.python.org/downloads)
   installation is silently assumed.

2. First of all, the dependency of the library,
   [`websocket-client`](http://pypi.python.org/pypi/websocket-client/) has to
   be installed (if it is not as yet). For that, either download and extract
   the source archive from the linked page and run the `setup.py` file, or —
   if you have `pip` installed — run

   ```
   pip install -v websocket-client
   ```

   **Important**: Depending on the Python version you want to use, you may
   have to adapt the command lines (`python setup.py` → `python3 setup.py`;
   `pip install -v websocket-client` → `pip3 install -v websocket-client`),
   or install the library for both Python versions (both `python setup.py`
   *and* `python3 setup.py`).

3. The installation of `basebot` itself is trivial, either copy the
   `basebot.py` file into the directory where you will store your source
   files, or to some location in the standard module search path.

4. **Done**!

## Testing / example bot

The best way to test whether the installation has succeeded is to run a bot.
For example, save the following source snippet (an expanded version of the
example bot in the `basebot.py` module documentation) into a file named
`testbot.py` in your source location (either the directory where
`basebot.py` lies, or anywhere if it is in the standard module path), and
start the bot from the command line by running `python testbot.py test` in
the corresponding directory. The bot should appear in the room
[*&test*](http://euphoria.io/room/test) under the nickname *test*.

```python
import sys, basebot

def frobnicator(match, info):
    return match.group(1)[::-1] # Reply with the string reversed.

def calculator(match, info):
    # Good code is self-explaining!
    val1, op, val2 = int(match.group(1)), match.group(2), int(match.group(3))
    if op == '+':
        result = val1 + val2
    elif op == '-':
        result = val1 - val2
    elif op == '*':
        result = val1 * val2
    elif op == '/':
        if val2 == 0:
            return 'Division by zero!'
        result = val1 / val2
    return 'Result: ' + str(result)

if __name__ == '__main__':
    basebot.run_minibot(sys.argv[1:], botname='TestBot', nickname='test',
        short_help='This is a test bot. For a bit more behavior, try '
            'posting a message with a single "test" at the beginning.',
        regexes={'^test$': 'Test!', '^test (.+)$': frobnicator,
                 '^!calc\s+(\d+)\s+([-+*/])\s+(\d+)$': calculator})
```

## Further/Advanced Notes

### Further reading

The best source of documentation about the library (I know about) is [the
library itself](basebot.py); read its inline docs for further information,
or use your favorite documentation generator.

### Alternative sites

The bot library has the domain name [euphoria.io](http://euphoria.io)
built-in as a default. If you want to run a bot at an alternative site,
you can achieve that by setting the `BASEBOT_ROOM_FORMAT` environment
variable. It will be `%`-interpolated by the bot library with the room name
to enter, and the library will try to connect to the resulting URL.

The default preset is `wss://euphoria.io/room/%s/ws`, therefore,
trying to enter the room `test` using the default settings would result
in an connection attempt to `wss://euphoria.io/room/test/ws`.
