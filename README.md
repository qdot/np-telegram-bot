# NP Telegram Bot

NP Telegram Bot is a simple code base for building bots with a few
predefined features on top of the
[python-telegram-bot](http://github.com/python-telegram-bot/python-telegram-bot)
API.

NP Telegram Bot offers the following modules on top of python-telegram-bot:

- User tracking with flags - Allows developers to create different
  user privileges for accessing bot actions and features.
- Group Tracking - Keeps a list of what groups the bot is in (how does
  telegram not have this as a feature yet?!), allows bot
  administrators to broadcast messages into all groups bot is
  currently a member of.
- Conversation Tracking - Uses python generators to make holding
  asynchronous conversations with users simple and painless.

# Why use this versus just python-telegram-bot?

If you're just planning to make a simple inline bot that will access a
web API and return results, then using this is probably overkill.
However, for anyone that wants to host a more IRC style bot that will
remember users, take user input, and maintain state between sessions,
NP Telegram Bot provides some handy tools to make getting up and
running a little easier.

# Requirements

Requirements for NP Telegram Bot are:

- Python 3 (tested on 3.5, but should work on 3.3+, and maybe even earlier)
- Redis backing store (Though could easily be swapped out with something else)

# Bots using NP Telegram Bot

- [Mowcounter](http://github.com/qdot/mowcounter-telegram-bot) -
  Simple chat focused bot that counts phrase usage among users and
  keeps a high score table.
