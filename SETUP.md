# basebot setup manual

## Abstract

This manual covers the complete installation process of the `basebot`
library, including launching an example bot.

## Installation

1. The presence of a working [Python](https://www.python.org/downloads)
   installation is silently assumed, including — depending on your desired way
   of installation — the `pip` tool with support for Git repositories.

2. First of all, the dependency of the library,
   [`websocket-server`](https://github.com/CylonicRaider/websocket-server/)
   has to be installed (if it is yet). For that, either download and extract
   the source archive from the linked page and run `setup.py install`, or run

   ```
   pip install -v git+https://github.com/CylonicRaider/websocket-server/
   ```

   Depending on the Python version (2 or 3) you want to use, you may have to
   adapt the command line.

   For convenience, a matching version of the library is bundled with
   `basebot`; to install it, ensure its Git submodule is up-to-date (by
   running `git submodule update --init`) and run `setup.py install` in the
   `.websocket-server` subdirectory.

3. The installation of `basebot` itself is trivial; download the source code
   and invoke `setup.py install` using the desired Python version, or run

   ```
   pip install -v git+https://github.com/CylonicRaider/basebot/
   ```

4. **Done**!

## Testing / example bot

The best way to test whether the installation has succeeded is to run a bot.
For example, save the following source snippet into a file named `testbot.py`
in your source location (either the directory where `basebot.py` lies, or
anywhere if the latter is in the standard module path), and start the bot
from the command line by running `python testbot.py test` in the
corresponding directory. The bot should appear in the room
[*&test*](https://euphoria.io/room/test) under the nickname *test*.

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
    basebot.run_minibot(botname='TestBot', nickname='test',
        short_help='This is a test bot. For a bit more behavior, try '
            'posting a message with a single "test" at the beginning.',
        regexes={'^test$': 'Test!', '^test (.+)$': frobnicator,
                 '^!calc\s+(\d+)\s*([-+*/])\s*(\d+)$': calculator})
```

## Further/advanced notes

### Further reading

For a fuller introduction, see [MANUAL.md](MANUAL.md).

The best source of documentation about the library (I know about) is [the
library itself](basebot.py); read its inline docs for further information,
or use your favorite documentation generator.

### Alternative sites

The bot library has the domain name [euphoria.io](https://euphoria.io)
built-in as a default. If you want to run a bot at an alternative site, you
can achieve that by setting the `BASEBOT_URL_TEMPLATE` environment variable,
or the `--url-template` command-line option. It is `{}`-formatted by the bot
library with the room name to enter, and the library tries to connect to the
resulting URL.

The default preset is `wss://euphoria.io/room/{}/ws`, therefore, trying
to enter the room `test` using the default settings would result in a
connection attempt to `wss://euphoria.io/room/test/ws`.
