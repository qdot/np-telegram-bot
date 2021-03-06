from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
from .permissioncommandhandler import PermissionCommandHandler
from .users import UserManager
from .conversations import ConversationManager, ConversationHandler
from .chats import ChatManager
from .blockdispatcher import BlockDispatcher
from threading import Thread
from functools import partial
import redis
import argparse
import logging
import configparser


class NPTelegramBot(object):
    FLAGS = ["admin", "def_edit", "user_flags"]

    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.config = config

        if "token" not in config:
            print("Cannot load token!")
            raise RuntimeError()
        tg_token = config["token"]

        if "redis_host" in config:
            redis_args = {}
            redis_args["host"] = config["redis_host"]
            redis_args["db"] = config["redis_db_num"]
            if "redis_port" in config:
                redis_args["port"] = config["redis_port"]
            if "redis_password" in config:
                redis_args["password"] = config["redis_password"]
            self.store = redis.StrictRedis(decode_responses=True,
                                           **redis_args)
        else:
            print("No backing store specified in config file!")
            raise RuntimeError()

        self.conversations = ConversationManager()
        self.users = UserManager(self.store)
        self.chats = ChatManager(self.store)
        self.chats.add_join_filter(self.chats.block_filter)

        self.thread = None
        self.updater = Updater(token=tg_token)
        self.dispatcher = BlockDispatcher(self.updater, self.users)

    @staticmethod
    def parse_cli_arguments():
        parser = argparse.ArgumentParser()
        parser.add_argument("-c", "--config", dest="config",
                            help="Configuration File to use")
        parser.add_argument("-b", "--bot", dest="bot",
                            help="Bot name from configuration file to use")
        args = parser.parse_args()

        if not args.config:
            parser.print_help()
            raise RuntimeError("Config file argument required!")

        if not args.bot:
            parser.print_help()
            raise RuntimeError("Bot name argument required!")

        try:
            config = configparser.ConfigParser()
            config.read(args.config)
        except:
            raise RuntimeError("Cannot read config file!")

        if args.bot not in config.sections():
            raise RuntimeError("Bot {0} not in config file!".format(args.bot))
        return config[args.bot]

    def setup_commands(self):
        # Make sure the message handlers are in different groups so they are
        # always run
        self.dispatcher.add_handler(MessageHandler([Filters.text],
                                                   self.handle_message),
                                    group=1)
        self.dispatcher.add_handler(MessageHandler([Filters.status_update],
                                                   self.chats.process_status_update),
                                    group=2)

        # Default commands These all require private message by default, just
        # so they don't possibly spam groups.
        self.dispatcher.add_handler(PermissionCommandHandler('start',
                                                             [self.require_privmsg],
                                                             self.handle_help))
        self.dispatcher.add_handler(PermissionCommandHandler('help',
                                                             [self.require_privmsg],
                                                             self.handle_help))
        self.dispatcher.add_handler(PermissionCommandHandler('settings',
                                                             [self.require_privmsg],
                                                             self.handle_help))
        self.dispatcher.add_handler(CommandHandler('cancel',
                                                   self.conversations.cancel))

        self.dispatcher.add_handler(PermissionCommandHandler('userregister',
                                                             [self.require_privmsg],
                                                             self.users.register))

        self.dispatcher.add_handler(ConversationHandler('useraddflag',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.conversations,
                                                        self.users.add_flag))

        self.dispatcher.add_handler(ConversationHandler('userrmflag',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.conversations,
                                                        self.users.remove_flag))

        self.dispatcher.add_handler(ConversationHandler('userblock',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.conversations,
                                                        self.users.block_user))

        self.dispatcher.add_handler(ConversationHandler('groupbroadcast',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.conversations,
                                                        self.chats.broadcast))
        self.dispatcher.add_handler(PermissionCommandHandler('grouplist',
                                                             [self.require_privmsg,
                                                              partial(self.require_flag, flag="admin")],
                                                             self.chats.list_known_chats))
        self.dispatcher.add_handler(ConversationHandler('groupleave',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.conversations,
                                                        self.chats.leave_chat))
        self.dispatcher.add_handler(ConversationHandler('groupblock',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.conversations,
                                                        partial(self.chats.leave_chat, block=True)))

        # self.dispatcher.add_handler(PermissionCommandHandler('outputcommands',
        #                                                      [self.require_privmsg,
        #                                                       partial(self.require_flag, flag="admin")],
        #                                                      self.output_commands))

        # On errors, just print to console and hope someone sees it
        self.dispatcher.add_error_handler(self.handle_error)

    def handle_help(self, bot, update):
        help_text = ["Hi! I'm an NP Telegram Bot! If I'm displaying this message, it means whoever wrote me didn't override the handle_help function. They should do that!"]
        bot.sendMessage(update.message.chat.id,
                        "\n".join(help_text),
                        parse_mode="HTML",
                        disable_web_page_preview=True)

    def handle_error(self, bot, update, error):
        # TODO Add ability for bot to message owner with stack traces
        self.logger.warn("Exception thrown! %s", error)

    def try_register(self, bot, update):
        user_id = update.message.from_user.id
        if not self.users.is_valid_user(user_id):
            self.users.register(bot, update)
        # Always returns true, as running any command will mean the user is
        # registered. We just want to make sure they're in the DB so flags can
        # be added if needed.
        return True

    # When used with PermissionCommandHandler, Function requires currying with
    # flag we want to check for.
    def require_flag(self, bot, update, flag):
        user_id = update.message.from_user.id
        if not self.users.is_valid_user(user_id) or not self.users.has_flag(user_id, flag):
            bot.sendMessage(update.message.chat.id,
                            text="You do not have the required permissions to run this command.")
            return False
        return True

    def require_privmsg(self, bot, update):
        if update.message.chat.id < 0:
            bot.sendMessage(update.message.chat.id,
                            reply_to_message_id=update.message.id,
                            text="Please message that command to me. Only the following commands are allowed in public chats:\n- /def")
            return False
        return True

    def output_commands(self, bot, update):
        command_str = ""
        for m in self.modules:
            command_str += m.commands() + "\n"
        bot.sendMessage(update.message.chat.id,
                        text=command_str)

    def handle_message(self, bot, update):
        # Ignore messages from groups
        if update.message.chat.id < 0:
            return
        if self.conversations.check(bot, update):
            return
        self.try_register(bot, update)
        self.handle_help(bot, update)

    def start_webhook_thread(self):
        if "webhook_url" not in self.config:
            print("No webhook URL to bind to!")
            raise RuntimeError()
        self.updater.bot.setWebhook(webhook_url=self.config["webhook_url"])
        # Steal the queue from the updater.
        self.update_queue = self.updater.update_queue
        self.thread = Thread(target=self.dispatcher.start, name='dispatcher')
        self.thread.start()

    def add_webhook_update(self, update):
        self.update_queue.put(update)

    def start_loop(self):
        self.updater.start_polling()
        self.updater.idle()

    def shutdown(self):
        if self.thread:
            self.thread.join(1)


def create_webhook_bot(config):
    bot = NPTelegramBot(config)
    bot.setup_commands()
    bot.start_webhook_thread()
    return bot
