# basebot programmer's manual

## Abstract

This document provides an overview over the entry points into writing bots
using `basebot`.

## Introduction

`basebot` supports two approaches to writing bots, a [procedural](#minibot)
and an [object-oriented](#bot) one. Both are equivalently powerful; however,
although simple bots are written quickly using the procedural approach,
implementing more complex functionality in it can become ugly as quickly.

Because the procedural approach builds upon the object-oriented, the latter
is explained first; you can [skip to the procedural one](#minibot) if you are
not interested.

## Bot

The main (and historically only) way to create new bots is to inherit from
the `basebot.Bot` class. Subclasses may override some class attributes to
provide normally static values:

- `BOTNAME`: The "codename" of the bot as used for logging.
- `NICKNAME`: The nickname to set when entering a room. If at the default of
  `None`, the bot will not set a nickname at all; some functionality will be
  unavailable.
- `SHORT_HELP`: If not `None`, this is replied with to the bare `!help`
  command, and if no `LONG_HELP` is set, it is used for the specific `!help`
  command. See the [botrulez](https://github.com/jedevc/botrulez) for advice
  on how to format help messages.
- `LONG_HELP`: If `None`, the specific `!help @BotName` command is not
  replied to. If at the default value of `Ellipsis` _(yes, that is a real
  singleton)_, the value of `SHORT_HELP` is used instead. Otherwise, this is
  replied with to a specific `!help` command.

The constructor of the subclass should pass all positional and keyword
arguments on to the parent class constructor. Some keyword arguments may be
passed to the parent class' constructor to tune responses to standard
commands; refer to the [reference](#further-reading) for details.

There is a plethora of handler methods subclasses can override; a few notable
ones are listed here:

### handle_chat — Live message processing

    handle_chat(msg : Message, meta : dict) -> None

This handler is invoked on "live" chat messages (in the library's parlance),
_i.e._ `send-event`-s, which correspond to users (or bots) posting new
messages.

- `msg` is a [`Message`](http://api.euphoria.io/#message) structure,
  presented as an instance of the `basebot.Record` class that is a dictionary
  exposing some items as attributes. The most interesting parts of it are
  found at:
    - `msg.id`: The ID of the message.
    - `msg.parent`: The ID of the parent of the message, or `None`.
    - `msg.sender.id`: The (agent) ID of the sender of the message.
    - `msg.sender.name`: The nickname of the sender of the message.
    - `msg.content`: The content of the message.

- `meta` is an ordinary dictionary holding miscellaneous meta-information
  about the message; most notable are:
    - `reply`: A convenience function that, when called, posts a message
      as a reply to the message currently being handled. As an additional
      argument, a callback may be specified that is called with the server's
      `send-reply` to "our" reply as an argument.

    Further members are omitted here; see the [reference](#further-reading)
    for a full listing.

The return value of `handle_chat` is ignored.

### handle_command — Command handling

    handle_command(cmdline : list, meta : dict) -> None

This handler is invoked when a "live" chat message (as elaborated above) is
in addition a bot command, _i.e._, the first non-whitespace character is an
exclamation mark `!`; the method is run after `handle_chat`.

- `cmdline` is a list of `Token`-s, _i.e._ strings with an additional
  `offset` attribute unambiguously identifying the position in the "parent"
  string (see below for how to reach it); the class does not implement
  anything beyond; all operations return bare strings. According to the
  [botrulez](https://github.com/jedevc/botrulez), the very first item of
  `cmdline` is the command name (including the leading `!`); further items
  are the arguments in their original order.

- `meta` is again an ordinary dictionary holding references to some objects
  of interest. Particularly interesting may be:
    - `line`: The entire unfiltered command line.
    - `msgid`: The ID of the message.
    - `sender`: The nickname of the author of the message.
    - `sender_id`: The (agent) ID of the sender.
    - `reply`, a convenience function for replying elaborated upon above.

The return value of `handle_command` is, again, ignored.

## Further reading

The inline documentation of [basebot.py](basebot.py) provides a thorough
reference of all components included.
